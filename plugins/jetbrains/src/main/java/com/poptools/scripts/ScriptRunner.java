package com.poptools.scripts;

import com.intellij.execution.ExecutionManager;
import com.intellij.execution.actions.StopProcessAction;
import com.intellij.execution.configurations.GeneralCommandLine;
import com.intellij.execution.executors.DefaultRunExecutor;
import com.intellij.execution.filters.TextConsoleBuilderFactory;
import com.intellij.execution.process.*;
import com.intellij.execution.ui.*;
import com.intellij.openapi.Disposable;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.project.*;
import com.intellij.openapi.ui.Messages;
import com.intellij.openapi.util.Disposer;
import com.intellij.openapi.util.Key;
import com.intellij.openapi.actionSystem.*;
import com.intellij.util.concurrency.AppExecutorUtil;
import com.intellij.util.execution.ParametersListUtil;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

public final class ScriptRunner {
    private static final Key<Set<String>> STARTING=Key.create("poptool.starting.scripts");
    private ScriptRunner() {}
    private static Set<String> starting(Project project) {
        Set<String> ids=project.getUserData(STARTING);
        if(ids==null){ids=new HashSet<>();project.putUserData(STARTING,ids);}return ids;
    }
    private static ScriptDescriptor existing(Project project,String id) {
        return ExecutionManager.getInstance(project).getContentManager().getAllDescriptors().stream()
            .filter(d->d instanceof ScriptDescriptor s && s.scriptId.equals(id)).map(d->(ScriptDescriptor)d).findFirst().orElse(null);
    }
    private static boolean alreadyRunning(Project project,String id) {
        ScriptDescriptor descriptor=existing(project,id);
        boolean active=descriptor!=null && descriptor.getProcessHandler()!=null && !descriptor.getProcessHandler().isProcessTerminated();
        if(active || starting(project).contains(id)) {
            if(descriptor!=null)ExecutionManager.getInstance(project).getContentManager().toFrontRunContent(DefaultRunExecutor.getRunExecutorInstance(),descriptor);
            return true;
        }return false;
    }
    public static void run(Project project,ScriptDefinition source,Map<String,String> previous) {
        if(project.isDisposed())return;
        if(alreadyRunning(project,source.id))return;
        ScriptDefinition script=ScriptJson.copy(source);
        try {
            ScriptJson.validate(script);
            String serial=AndroidDevices.needed(script)?AndroidDevices.selectedSerial(project):null;
            Map<String,String> values=new LinkedHashMap<>();
            if(!script.parameters.isEmpty()) {
                ParameterDialog dialog=new ParameterDialog(project,script,previous);
                if(!dialog.showAndGet())return;values.putAll(dialog.values());
            }
            if(script.presentation.confirm_before_run && Messages.showYesNoDialog(project,"执行脚本“"+script.title+"”？","确认执行",Messages.getQuestionIcon())!=Messages.YES)return;
            Map<String,String> settings=ScriptLibrary.getInstance().paths();
            String base=project.getBasePath();
            if(alreadyRunning(project,script.id))return;
            starting(project).add(script.id);
            ApplicationManager.getApplication().executeOnPooledThread(()->launch(project,script,values,settings,base,serial));
        } catch(Exception e) { starting(project).remove(script.id);Messages.showErrorDialog(project,Objects.toString(e.getMessage(),e.toString()),"脚本无法运行"); }
    }

    private static void launch(Project project,ScriptDefinition script,Map<String,String> values,Map<String,String> settings,String base,String serial) {
        Path temporary=null;
        try {
            if(project.isDisposed())return;
            String dir=script.executor.cwd==null || script.executor.cwd.isBlank()?base:ParameterTemplates.render(script.executor.cwd,values);
            if(dir==null)throw new IllegalArgumentException("当前项目没有根目录，请为脚本指定绝对工作目录");
            Path cwd=Path.of(dir);if(!cwd.isAbsolute()) {if(base==null)throw new IllegalArgumentException("相对工作目录需要项目根目录");cwd=Path.of(base).resolve(cwd);}
            if(!Files.isDirectory(cwd))throw new IllegalArgumentException("工作目录不存在："+cwd);
            EnvironmentResolver resolver=new EnvironmentResolver(settings,System.getenv());
            String type=script.executor.kind;String interpreter=type.equals("batch")?"cmd":type;
            String command=ParameterTemplates.render(script.executor.command,values);
            List<String> args=ParameterTemplates.renderArguments(script.executor.args,values,script.parameters);
            List<String> launchArgs=new ArrayList<>();
            Path executable;
            if(type.equals("process"))executable=resolver.resolve(command,script.interpreter);
            else executable=resolver.resolve(interpreter,script.interpreter);
            List<String> dependencies=new ArrayList<>(script.executor.requirements.stream().filter(r->!r.equals("android_device")).toList());
            if(serial!=null && !dependencies.contains("adb"))dependencies.add("adb");
            Map<String,String> environment=resolver.executionEnvironment(dependencies);
            if(serial!=null)environment.put("ANDROID_SERIAL",serial);
            script.executor.env.forEach((k,v)->environment.put(k,ParameterTemplates.render(v,values)));
            environment.put("PYTHONUTF8","1");environment.put("PYTHONIOENCODING","utf-8");environment.put("PYTHONUNBUFFERED","1");
            temporary=Files.createTempDirectory("poptool-script-");
            environment.put("POPTOOLS_OUTPUT_DIR",Files.createDirectories(temporary.resolve("outputs")).toString());
            List<String> parts=ParametersListUtil.parse(command);
            Path file=null;
            if(!parts.isEmpty() && !command.contains("\n")) {
                try {Path candidate=cwd.resolve(parts.getFirst());if(Files.isRegularFile(candidate))file=candidate;}catch(InvalidPathException ignored){}
            }
            switch(type) {
                case "python" -> {
                    if(file!=null){launchArgs.add(file.toString());launchArgs.addAll(parts.subList(1,parts.size()));}
                    else {Path src=temporary.resolve("script.py");Files.writeString(src,command,StandardCharsets.UTF_8);launchArgs.add(src.toString());}
                    launchArgs.addAll(args);
                }
                case "powershell" -> {
                    launchArgs.addAll(List.of("-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-Command"));
                    String setup="$OutputEncoding = [System.Text.UTF8Encoding]::new($false); [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; ";
                    launchArgs.add(setup+command);launchArgs.addAll(args);
                }
                case "bash" -> {launchArgs.addAll(List.of("-c",command,"poptool-script"));launchArgs.addAll(args);}
                case "batch" -> {
                    if(file==null){file=temporary.resolve("script.cmd");Files.writeString(file,"@chcp 65001 >nul\r\n"+command.replace("\r\n","\n").replace("\r","\n").replace("\n","\r\n"),StandardCharsets.UTF_8);}
                    launchArgs.addAll(List.of("/d","/q","/c",file.toString()));launchArgs.addAll(args);
                }
                default -> launchArgs.addAll(args);
            }
            GeneralCommandLine line=new GeneralCommandLine(executable.toString()).withParameters(launchArgs).withWorkDirectory(cwd.toFile()).withCharset(Charset.forName(script.executor.encoding));
            line.withParentEnvironmentType(GeneralCommandLine.ParentEnvironmentType.NONE).withEnvironment(environment);
            if(project.isDisposed()){deleteTemporarySources(temporary);return;}
            ScriptProcessHandler handler=new ScriptProcessHandler(line);
            // EOF: scripts requiring interactive stdin are outside the first-version contract.
            if(handler.getProcessInput()!=null)handler.getProcessInput().close();
            Path cleanup=temporary;
            handler.addProcessListener(new ProcessAdapter(){@Override public void processTerminated(ProcessEvent e){deleteTemporarySources(cleanup);}});
            Disposable lifetime=Disposer.newDisposable("PopTool "+script.title);
            Disposer.register(lifetime,()->{if(!handler.isProcessTerminated())handler.destroyProcess();});
            ApplicationManager.getApplication().invokeLater(()->{
                if(project.isDisposed()){handler.destroyProcess();handler.startNotify();return;}
                Disposer.register(project,lifetime);
                ConsoleView console=TextConsoleBuilderFactory.getInstance().createBuilder(project).getConsole();
                console.attachToProcess(handler);
                console.print("运行："+script.title+"\n"+(serial==null?"":"默认 Android 设备："+serial+"（脚本显式设备参数优先）\n"),ConsoleViewContentType.SYSTEM_OUTPUT);
                console.print("脚本输出目录："+cleanup.resolve("outputs")+"\n",ConsoleViewContentType.SYSTEM_OUTPUT);
                AnAction again=new DumbAwareAction("再次运行") { @Override public void actionPerformed(AnActionEvent e){
                    ScriptDefinition latest=ScriptLibrary.getInstance().list(false).stream().filter(s->s.id.equals(script.id)).findFirst().orElse(script);
                    run(project,latest,values);
                } };
                AnAction stop=new StopProcessAction("停止","停止本次脚本及子进程",handler);
                JPanelWithToolbar content=new JPanelWithToolbar(console,again,stop);
                ScriptDescriptor descriptor=new ScriptDescriptor(console,handler,content,script.title,script.id);
                Disposer.register(lifetime,console);
                Disposer.register(descriptor,()->Disposer.dispose(lifetime));
                handler.addProcessListener(new ProcessAdapter(){@Override public void processTerminated(ProcessEvent e){
                    console.print("\n"+(handler.stopped?"运行已停止":"退出码："+e.getExitCode())+"\n",ConsoleViewContentType.SYSTEM_OUTPUT);
                    deleteTemporarySources(cleanup);
                }});
                var manager=ExecutionManager.getInstance(project).getContentManager();
                ScriptDescriptor previous=existing(project,script.id);
                // Enable reuse only for this explicit pair. Other IDE runs cannot take these tabs.
                if(previous!=null) {
                    previous.reusing=true;descriptor.reusing=true;
                    try{manager.showRunContent(DefaultRunExecutor.getRunExecutorInstance(),descriptor,previous);}
                    finally{previous.reusing=false;descriptor.reusing=false;}
                }else manager.showRunContent(DefaultRunExecutor.getRunExecutorInstance(),descriptor);
                handler.startNotify();
                if(script.executor.timeout_seconds!=null){
                    ScheduledFuture<?> timeout=AppExecutorUtil.getAppScheduledExecutorService().schedule(()->{if(!handler.isProcessTerminated()){
                        console.print("\n执行超时，正在停止。\n",ConsoleViewContentType.ERROR_OUTPUT);handler.destroyProcess();
                    }},script.executor.timeout_seconds,TimeUnit.SECONDS);
                    handler.addProcessListener(new ProcessAdapter(){@Override public void processTerminated(ProcessEvent e){timeout.cancel(false);}});
                    if(handler.isProcessTerminated())timeout.cancel(false);
                }
            });
        } catch(Exception e) {
            if(temporary!=null)deleteTemporarySources(temporary);
            ApplicationManager.getApplication().invokeLater(()->{if(!project.isDisposed())Messages.showErrorDialog(project,Objects.toString(e.getMessage(),e.toString()),"脚本无法运行");});
        } finally {
            ApplicationManager.getApplication().invokeLater(()->{if(!project.isDisposed())starting(project).remove(script.id);});
        }
    }
    private static final class ScriptDescriptor extends RunContentDescriptor {
        final String scriptId;
        boolean reusing;
        ScriptDescriptor(ConsoleView console,ProcessHandler handler,javax.swing.JComponent content,String title,String id) {
            super(console,handler,content,title);scriptId=id;
            setReusePolicy(new RunContentDescriptorReusePolicy(){@Override public boolean canBeReusedBy(RunContentDescriptor other){return other instanceof ScriptDescriptor s && scriptId.equals(s.scriptId);}});
        }
        @Override public boolean isContentReuseProhibited(){return !reusing;}
    }
    private static void deleteTemporarySources(Path dir) {
        // Keep generated outputs; remove only source files created by this launcher.
        for(String name:List.of("script.py","script.cmd")){try{Files.deleteIfExists(dir.resolve(name));}catch(Exception ignored){}}
        try{Files.deleteIfExists(dir.resolve("outputs"));}catch(Exception ignored){}
        try{Files.deleteIfExists(dir);}catch(Exception ignored){}
    }
    public static final class ScriptProcessHandler extends KillableColoredProcessHandler {
        volatile boolean stopped;
        public ScriptProcessHandler(GeneralCommandLine line) throws com.intellij.execution.ExecutionException {super(line);setShouldDestroyProcessRecursively(true);}
        @Override protected void destroyProcessImpl() { stopped=true;super.destroyProcessImpl(); }
    }
    private static final class JPanelWithToolbar extends javax.swing.JPanel {
        JPanelWithToolbar(ConsoleView console,AnAction... actions){super(new java.awt.BorderLayout());
            DefaultActionGroup group=new DefaultActionGroup(actions);ActionToolbar toolbar=ActionManager.getInstance().createActionToolbar("PopToolRun",group,true);
            toolbar.setTargetComponent(this);add(toolbar.getComponent(),java.awt.BorderLayout.NORTH);add(console.getComponent());
        }
    }
}

package com.poptools.scripts;

import com.intellij.openapi.startup.StartupActivity;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.editor.EditorFactory;
import com.intellij.openapi.options.ShowSettingsUtil;
import com.intellij.openapi.util.Disposer;
import com.intellij.openapi.wm.ToolWindowManager;
import com.intellij.execution.ExecutionManager;
import com.intellij.execution.impl.ConsoleViewImpl;
import com.intellij.execution.ui.RunContentDescriptor;
import com.intellij.util.concurrency.AppExecutorUtil;
import org.jetbrains.plugins.terminal.TerminalToolWindowManager;
import org.jetbrains.plugins.terminal.TerminalTabState;
import org.jetbrains.plugins.terminal.TerminalEngine;
import com.intellij.terminal.JBTerminalWidget;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Included only in the isolated smoke-test package, never in the release ZIP. */
public final class IntegrationSmoke implements StartupActivity.DumbAware {
    private Path report;
    private Project project;
    private final List<String> checks=new ArrayList<>();
    private long started;
    private final List<String> runningTitles=new ArrayList<>();
    private boolean stopRequested;
    private ScriptDefinition repeated;
    private com.intellij.ui.content.Content reusedContent;
    private int expectedTabs;
    private boolean activeDuplicateChecked;
    private int reusePhase;
    private boolean previewComplete;
    @Override public void runActivity(Project project){
        this.project=project;report=Path.of(System.getProperty("poptool.smoke.report"));started=System.currentTimeMillis();
        ApplicationManager.getApplication().invokeLater(()->{
            try{
                var manager=ToolWindowManager.getInstance(project);
                var window=manager.getToolWindow("NicoTools");
                if(window==null)throw new AssertionError("tool window not registered");
                window.show();check(window.getContentManager().getContentCount()>0,"tool window initialized");
                check(window.getIcon()!=null,"NicoTools tool window icon loaded");
                var logo=com.intellij.openapi.util.IconLoader.getIcon("/META-INF/pluginIcon.svg",ScriptToolWindow.class);
                check(logo.getIconWidth()==40 && logo.getIconHeight()==40,"NicoTools plugin logo loads at 40px");
                var logoImage=new java.awt.image.BufferedImage(240,240,java.awt.image.BufferedImage.TYPE_INT_ARGB);
                var logoGraphics=logoImage.createGraphics();logoGraphics.scale(6,6);logo.paintIcon(null,logoGraphics,0,0);logoGraphics.dispose();
                javax.imageio.ImageIO.write(logoImage,"png",report.getParent().resolve("nicotools-icon-preview.png").toFile());
                var plugin=com.intellij.ide.plugins.PluginManagerCore.getPlugin(com.intellij.openapi.extensions.PluginId.getId("com.poptools.scripts"));
                check(plugin!=null && plugin.getName().equals("NicoTools"),"plugin display name is NicoTools");
                var action=ActionManager.getInstance().getAction("PopTool.NewFromTerminal");check(action!=null,"terminal action registered");
                var group=(DefaultActionGroup)ActionManager.getInstance().getAction("Terminal.ReworkedTerminalContextMenu");
                check(Arrays.asList(group.getChildren(ActionManager.getInstance())).contains(action),"reworked terminal menu contains action");
                var terminalManager=TerminalToolWindowManager.getInstance(project);
                var state=new TerminalTabState();state.myWorkingDirectory=project.getBasePath();state.myTabName="PopTool Smoke Classic";state.myShellCommand=List.of("cmd.exe");
                var widget=terminalManager.createNewTab(TerminalEngine.CLASSIC,state,null);
                JBTerminalWidget classic=JBTerminalWidget.asJediTermWidget(widget);
                check(classic!=null,"classic terminal created");
                boolean found=false;
                for(var provider=classic;provider!=null;){
                    if(provider.getActions().stream().anyMatch(a->a.getName().equals("新建 NicoTools 自定义脚本"))){found=true;break;}
                    // provider chains contain arbitrary TerminalActionProvider implementations.
                    var next=provider.getNextProvider();if(next!=null){found=containsClassicAction(next);break;}else break;
                }
                check(found,"classic terminal action chain contains action");
                var selectionTerminal=new JBTerminalWidget(project,classic.getSettingsProvider(),project);
                selectionTerminal.writePlainMessage("中文\n  echo hello");
                selectionTerminal.getTerminalPanel().selectAll();
                String terminalText=selectionTerminal.getSelectedText();
                check(terminalText!=null && terminalText.contains("中文\n  echo hello"),"native classic terminal selection preserves multiline text");
                DataContext terminalContext=id->JBTerminalWidget.SELECTED_TEXT_DATA_KEY.is(id)?selectionTerminal.getSelectedText():CommonDataKeys.PROJECT.is(id)?project:null;
                var terminalEvent=AnActionEvent.createFromAnAction(action,null,"Terminal",terminalContext);
                check(terminalText.equals(NewFromTerminalAction.selection(terminalEvent)),"terminal action reads native selected text unchanged");
                action.update(terminalEvent);check(terminalEvent.getPresentation().isEnabled(),"terminal action enabled for native selection");
                selectionTerminal.dispose();
                var editor=EditorFactory.getInstance().createEditor(EditorFactory.getInstance().createDocument("中文\n  echo hello"),project);
                editor.getSelectionModel().setSelection(0,editor.getDocument().getTextLength());
                DataContext ctx=id->CommonDataKeys.EDITOR.is(id)?editor:CommonDataKeys.PROJECT.is(id)?project:null;
                var event=AnActionEvent.createFromAnAction(action,null,"Terminal.ReworkedTerminalContextMenu",ctx);
                check(NewFromTerminalAction.selection(event).equals("中文\n  echo hello"),"editor selection preserves multiline indentation");
                EditorFactory.getInstance().releaseEditor(editor);
                var settings=new EnvironmentSettings();check(settings.createComponent()!=null,"environment settings construct");settings.disposeUIResources();
                try{AndroidDevices.selectedSerial(project);throw new AssertionError("empty project unexpectedly has a selected device");}
                catch(IllegalArgumentException expected){check(expected.getMessage().contains("选择"),"real Android device selection service rejects missing target");}
                ScriptDefinition s=new ScriptDefinition();s.title="PopTool smoke script";s.executor.command="Write-Output '中文 stdout'; [Console]::Error.WriteLine('stderr smoke'); exit 7";
                ScriptLibrary.getInstance().save(s,false);check(ScriptLibrary.getInstance().list(false).size()==1,"library save/read");
                repeated=s;
                var panel=(ScriptToolWindow.ScriptPanel)window.getContentManager().getContent(0).getComponent();
                var toolbarActions=panel.globalActions.getChildren(ActionManager.getInstance());
                check(Arrays.stream(toolbarActions).map(a->a.getTemplatePresentation().getText()).toList().equals(List.of("新建脚本","批量操作","导入","环境路径")),"only four global toolbar actions remain");
                check(Arrays.stream(toolbarActions).allMatch(a->a.getTemplatePresentation().getIcon()!=null),"all global toolbar actions have native icons");
                var menu=panel.createScriptMenu(s);
                var menuActions=((DefaultActionGroup)menu.getActionGroup()).getChildren(ActionManager.getInstance());
                check(Arrays.stream(menuActions).filter(a->!(a instanceof Separator)).map(a->a.getTemplatePresentation().getText()).toList().equals(List.of("执行脚本","编辑脚本","分享脚本","删除脚本")),"per-script context menu contains all four operations");
                check(menuActions.length==5 && menuActions[3] instanceof Separator,"delete action has a native menu separator");
                var scriptList=panel.scriptTable;
                check(scriptList.getColumnCount()==3 && scriptList.getColumnName(0).equals("名称"),"native script table has name type description columns");
                check(!scriptList.isCellEditable(0,0),"script rows remain read only");
                scriptList.setSize(600,300);
                var row=scriptList.getCellRect(0,0,true);
                check(panel.scriptAt(new java.awt.Point(5,row.y+row.height/2)).id.equals(s.id),"clicked row resolves correct script");
                check(panel.scriptAt(new java.awt.Point(5,row.y+row.height+20))==null,"blank list area does not resolve last script");
                var dialog=new ScriptEditor(project,s,false);check(dialog.getContentPane()!=null,"script editor constructs");Disposer.dispose(dialog.getDisposable());
                var help=new TemplateHelpDialog(project);check(help.getContentPane()!=null,"original PopTool template examples construct");Disposer.dispose(help.getDisposable());
                snapshotScriptPanel(panel,s);
                scriptList.dispatchEvent(new java.awt.event.MouseEvent(scriptList,java.awt.event.MouseEvent.MOUSE_CLICKED,System.currentTimeMillis(),0,5,row.y+row.height/2,2,false,java.awt.event.MouseEvent.BUTTON1));
                runningTitles.add(s.title);
                runFixture("batch","echo 中文 stdout\necho stderr smoke 1>&2\nexit /b 7","");
                runFixture("python","import sys; print('中文 stdout'); print('stderr smoke', file=sys.stderr); sys.exit(7)",System.getProperty("poptool.smoke.python",""));
                runFixture("bash","printf '中文 stdout\\n'; printf 'stderr smoke\\n' >&2; exit 7",System.getProperty("poptool.smoke.bash",""));
                ScriptDefinition process=new ScriptDefinition();process.title="PopTool smoke process";process.executor.kind="process";process.executor.command="cmd";
                process.executor.args=List.of("/d","/c","echo stdout smoke & echo stderr smoke 1>&2 & exit /b 7");
                ScriptRunner.run(project,process,Map.of());runningTitles.add(process.title);
                ScriptDefinition longRun=new ScriptDefinition();longRun.title="PopTool smoke stop";longRun.executor.command="Write-Output 'ready to stop'; Start-Sleep -Seconds 120";
                ScriptRunner.run(project,longRun,Map.of());
                write("RUNNING");poll();
            }catch(Throwable error){fail(error);}
        });
    }
    private void runFixture(String kind,String command,String interpreter) {
        ScriptDefinition s=new ScriptDefinition();s.title="PopTool smoke "+kind;s.executor.kind=kind;s.executor.command=command;s.interpreter=interpreter;
        ScriptRunner.run(project,s,Map.of());runningTitles.add(s.title);
    }
    private void snapshotScriptPanel(ScriptToolWindow.ScriptPanel panel,ScriptDefinition original) throws Exception {
        List<ScriptDefinition> examples=new ArrayList<>();
        String[] titles={"查看设备信息","导出应用日志","批量处理文件"},kinds={"powershell","bash","python"},descriptions={"读取当前选中设备的系统属性","导出日志到指定目录","按参数处理项目中的文件"};
        for(int i=0;i<titles.length;i++){var sample=new ScriptDefinition();sample.title=titles[i];sample.description=descriptions[i];sample.executor.kind=kinds[i];sample.executor.command="echo preview";ScriptLibrary.getInstance().save(sample,false);examples.add(sample);}
        // The smoke IDE launcher is hidden; use a temporary visible test host for native popup layout.
        var preview=new ScriptToolWindow.ScriptPanel(project);
        var host=new javax.swing.JFrame("NicoTools UI verification");
        host.setDefaultCloseOperation(javax.swing.WindowConstants.DISPOSE_ON_CLOSE);
        host.setContentPane(preview);host.setSize(740,400);host.setLocationRelativeTo(null);host.setVisible(true);
        ApplicationManager.getApplication().invokeLater(()->{
            try {
                preview.setSize(720,360);layout(preview);preview.toolbar.updateActionsImmediately();
                preview.scriptTable.setRowSelectionInterval(1,1);
                var popup=preview.createScriptMenu(examples.getFirst()).getComponent();
                popup.show(preview.scriptTable,180,preview.scriptTable.getRowHeight()*2);
                AppExecutorUtil.getAppScheduledExecutorService().schedule(()->ApplicationManager.getApplication().invokeLater(()->{
                    try {
                        preview.setSize(720,360);layout(preview);preview.scriptTable.setRowSelectionInterval(1,1);
                        var image=new java.awt.image.BufferedImage(720,360,java.awt.image.BufferedImage.TYPE_INT_ARGB);
                        var graphics=image.createGraphics();preview.paint(graphics);
                        graphics.translate(180,preview.getComponent(0).getHeight()+preview.scriptTable.getTableHeader().getHeight()+preview.scriptTable.getRowHeight()*2);
                        popup.printAll(graphics);graphics.dispose();
                        javax.imageio.ImageIO.write(image,"png",report.getParent().resolve("nicotools-script-list.png").toFile());
                        check(popup.getComponentCount()>=4,"native context menu materializes in IDE");
                    }catch(Throwable error){fail(error);}
                    finally{popup.setVisible(false);host.dispose();examples.forEach(sample->ScriptLibrary.getInstance().delete(sample.id,false));previewComplete=true;}
                }),500,TimeUnit.MILLISECONDS);
            }catch(Throwable error){host.dispose();fail(error);}
        });
    }
    private static void layout(java.awt.Container component){component.doLayout();for(var child:component.getComponents())if(child instanceof java.awt.Container container)layout(container);}
    private boolean containsClassicAction(com.jediterm.terminal.ui.TerminalActionProvider provider){
        for(var p=provider;p!=null;p=p.getNextProvider())if(p.getActions().stream().anyMatch(a->a.getName().equals("新建 NicoTools 自定义脚本")))return true;return false;
    }
    private void poll(){
        AppExecutorUtil.getAppScheduledExecutorService().schedule(()->ApplicationManager.getApplication().invokeLater(()->{
            try {
                var descriptors=ExecutionManager.getInstance(project).getContentManager().getAllDescriptors();
                for(String title:new ArrayList<>(runningTitles)) {
                    RunContentDescriptor descriptor=descriptors.stream().filter(d->d.getDisplayName().equals(title)).findFirst().orElse(null);
                    if(descriptor==null || !descriptor.getProcessHandler().isProcessTerminated())continue;
                    ConsoleViewImpl console=(ConsoleViewImpl)descriptor.getExecutionConsole();console.flushDeferredText();String text=console.getEditor().getDocument().getText();
                    check(text.contains(title.endsWith("process")?"stdout smoke":"中文 stdout"),title+" console stdout/UTF-8");check(text.contains("stderr smoke"),title+" console stderr");
                    check(text.contains("退出码：7"),title+" console exit status");
                    check(descriptor.getProcessHandler().getExitCode()==7,title+" external process exit code");runningTitles.remove(title);
                }
                var longRun=descriptors.stream().filter(d->d.getDisplayName().equals("PopTool smoke stop")).findFirst().orElse(null);
                if(longRun!=null && !stopRequested) {
                    ConsoleViewImpl console=(ConsoleViewImpl)longRun.getExecutionConsole();console.flushDeferredText();
                    if(console.getEditor().getDocument().getText().contains("ready to stop")){longRun.getProcessHandler().destroyProcess();stopRequested=true;}
                }
                if(previewComplete && runningTitles.isEmpty() && longRun!=null && longRun.getProcessHandler().isProcessTerminated()) {
                    if(reusePhase==0) {
                        check(stopRequested,"concurrent long-running process stopped independently");
                        var original=descriptors.stream().filter(d->d.getDisplayName().equals(repeated.title)).findFirst().orElseThrow();
                        reusedContent=original.getAttachedContent();expectedTabs=descriptors.size();
                        repeated.title="PopTool smoke renamed";
                        repeated.executor.command="Write-Output 'rerun marker'; Start-Sleep -Seconds 2; exit 3";
                        ScriptLibrary.getInstance().save(repeated,false);
                        ScriptRunner.run(project,repeated,Map.of());ScriptRunner.run(project,repeated,Map.of());
                        reusePhase=1;poll();return;
                    }
                    var rerun=descriptors.stream().filter(d->d.getDisplayName().equals(repeated.title)).findFirst().orElse(null);
                    if(rerun==null){poll();return;}
                    if(reusePhase==1 && !activeDuplicateChecked && !rerun.getProcessHandler().isProcessTerminated()) {
                        ScriptRunner.run(project,repeated,Map.of());activeDuplicateChecked=true;
                    }
                    if(!rerun.getProcessHandler().isProcessTerminated()){poll();return;}
                    ConsoleViewImpl rerunConsole=(ConsoleViewImpl)rerun.getExecutionConsole();rerunConsole.flushDeferredText();
                    String rerunText=rerunConsole.getEditor().getDocument().getText();
                    check(rerunText.contains("rerun marker") && rerun.getProcessHandler().getExitCode()==3,"repeat run prints new output and exit code");
                    check(!rerunText.contains("中文 stdout"),"repeat run clears previous output");
                    check(descriptors.size()==expectedTabs,"repeat and duplicate clicks do not add console tabs");
                    if(reusePhase==1) {
                        check(rerun.getAttachedContent()==reusedContent,"same script reuses original tab after title changes");
                        check(activeDuplicateChecked,"active repeat execution focuses existing process");
                        check(descriptors.stream().anyMatch(d->d.getDisplayName().equals("PopTool smoke python")),"reuse preserves other script tabs");
                        ExecutionManager.getInstance(project).getContentManager().removeRunContent(com.intellij.execution.executors.DefaultRunExecutor.getRunExecutorInstance(),rerun);
                        ScriptRunner.run(project,repeated,Map.of());reusePhase=2;poll();return;
                    }
                    check(rerun.getAttachedContent()!=reusedContent,"closed tab can be recreated on next run");
                    ApplicationManager.getApplication().saveSettings();check(Files.exists(Path.of(System.getProperty("idea.config.path"),"options","poptool-scripts.xml")),"library persisted to isolated config");
                    write("PASS");ApplicationManager.getApplication().exit(true,true,false);return;
                }
                write("RUNNING; pending="+runningTitles+"; descriptors="+descriptors.stream().map(RunContentDescriptor::getDisplayName).toList());
                if(System.currentTimeMillis()-started>90000)throw new AssertionError("console process did not complete within 90s");poll();
            }catch(Throwable error){fail(error);}
        }),1,TimeUnit.SECONDS);
    }
    private void check(boolean ok,String label){if(!ok)throw new AssertionError(label);checks.add("PASS "+label);}
    private void write(String status){try{Files.writeString(report,status+"\n"+String.join("\n",checks));}catch(Exception e){throw new RuntimeException(e);}}
    private void fail(Throwable error){checks.add("FAIL "+error);for(var f:error.getStackTrace())checks.add("  "+f);write("FAIL");ApplicationManager.getApplication().exit(true,true,false);}
}

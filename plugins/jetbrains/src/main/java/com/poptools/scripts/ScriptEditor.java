package com.poptools.scripts;

import com.google.gson.*;
import com.google.gson.reflect.TypeToken;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.ui.*;
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory;
import javax.swing.*;
import java.awt.*;
import java.util.*;

public final class ScriptEditor extends DialogWrapper {
    private final Project project;
    private final ScriptDefinition script;
    private final boolean template;
    private final java.util.List<String> originalTemplates;
    private final JTextField title=new JTextField(), description=new JTextField(), requirements=new JTextField();
    private final JTextArea body=new JTextArea(18,75),args=new JTextArea(4,65),env=new JTextArea(4,65),metadata=new JTextArea(9,65);
    private final JComboBox<String> kind=new JComboBox<>(new String[]{"powershell","python","bash","batch","process"});
    private final JComboBox<String> device=new JComboBox<>(new String[]{"auto","use","none"});
    private final TextFieldWithBrowseButton cwd=new TextFieldWithBrowseButton(),interpreter=new TextFieldWithBrowseButton();
    private final JTextField encoding=new JTextField(), timeout=new JTextField();
    public ScriptEditor(Project project,ScriptDefinition source,boolean template) {
        super(project);this.project=project;this.script=ScriptJson.copy(source);this.template=template;
        this.originalTemplates=ParameterTemplates.templates(source);
        setTitle(template?"编辑脚本模板":"编辑自定义脚本");setOKButtonText("保存");
        title.setText(script.title);description.setText(script.description);body.setText(script.executor.command);
        kind.setSelectedItem(script.executor.kind);device.setSelectedItem(script.executor.android_device_mode);
        requirements.setText(String.join(", ",script.executor.requirements));cwd.setText(Objects.toString(script.executor.cwd,""));
        interpreter.setText(script.interpreter);encoding.setText(script.executor.encoding);
        timeout.setText(script.executor.timeout_seconds==null?"":script.executor.timeout_seconds.toString());
        args.setText(ScriptJson.GSON.toJson(script.executor.args));env.setText(ScriptJson.GSON.toJson(script.executor.env));
        metadata.setText(ScriptJson.GSON.toJson(script.parameters));
        cwd.addBrowseFolderListener(project,FileChooserDescriptorFactory.createSingleFolderDescriptor());
        interpreter.addBrowseFolderListener(project,FileChooserDescriptorFactory.createSingleFileDescriptor());
        body.setFont(new Font(Font.MONOSPACED,Font.PLAIN,13));init();
    }
    @Override protected JComponent createCenterPanel() {
        JTabbedPane tabs=new JTabbedPane();JPanel main=new JPanel(new BorderLayout(5,5));
        JPanel form=new JPanel(new GridLayout(0,2,6,6));
        add(form,"名称",title);add(form,"说明",description);add(form,"执行类型",kind);add(form,"Android 设备（auto/use/none）",device);
        main.add(form,BorderLayout.NORTH);main.add(new JScrollPane(body),BorderLayout.CENTER);
        JPanel help=new JPanel(new BorderLayout(5,5));
        help.add(new JLabel("${参数:默认值} · ${模式:开启=1|关闭=0} · ${文件@file} · Var id = ${显示名称}"));
        JButton examples=new JButton("脚本模板与参数语法");examples.addActionListener(e->new TemplateHelpDialog(project).show());
        help.add(examples,BorderLayout.EAST);main.add(help,BorderLayout.SOUTH);
        tabs.addTab("脚本",main);
        JPanel options=new JPanel(new GridLayout(0,2,6,6));
        add(options,"工作目录（空为当前项目根目录）",cwd);add(options,"解释器路径（空为全局设置/系统环境）",interpreter);
        add(options,"依赖工具（逗号分隔）",requirements);add(options,"输出编码",encoding);add(options,"超时秒数（空为不限）",timeout);
        add(options,"参数数组 JSON（每项为一个独立参数）",new JScrollPane(args));add(options,"环境变量对象 JSON",new JScrollPane(env));
        tabs.addTab("执行配置",options);
        JPanel parameters=new JPanel(new BorderLayout(5,5));parameters.add(new JLabel("高级参数元数据 JSON：保留 PopTool 类型、必填、默认值及选项。新占位符在保存时生成。"),BorderLayout.NORTH);
        parameters.add(new JScrollPane(metadata));tabs.addTab("参数元数据",parameters);
        tabs.setPreferredSize(new Dimension(850,560));return tabs;
    }
    private static void add(JPanel panel,String label,Component field) { panel.add(new JLabel(label));panel.add(field); }
    @Override protected void doOKAction() {
        try {
            script.title=title.getText().strip();script.description=description.getText();script.executor.command=body.getText();
            script.executor.kind=(String)kind.getSelectedItem();script.executor.android_device_mode=(String)device.getSelectedItem();
            script.executor.cwd=cwd.getText().isBlank()?null:cwd.getText().strip();script.interpreter=interpreter.getText().strip();
            script.executor.encoding=encoding.getText().strip();script.executor.timeout_seconds=timeout.getText().isBlank()?null:Integer.valueOf(timeout.getText().strip());
            if(script.executor.timeout_seconds!=null && script.executor.timeout_seconds<1) throw new IllegalArgumentException("超时必须大于零");
            script.executor.requirements=new ArrayList<>(Arrays.stream(requirements.getText().split(",")).map(String::strip).filter(s->!s.isEmpty()).toList());
            script.executor.args=ScriptJson.GSON.fromJson(args.getText(),new TypeToken<java.util.List<String>>(){}.getType());
            script.executor.env=ScriptJson.GSON.fromJson(env.getText(),new TypeToken<Map<String,String>>(){}.getType());
            java.util.List<ScriptDefinition.Parameter> existing=ScriptJson.GSON.fromJson(metadata.getText(),new TypeToken<java.util.List<ScriptDefinition.Parameter>>(){}.getType());
            if(existing==null || script.executor.args==null || script.executor.env==null) throw new IllegalArgumentException("JSON 不能为 null");
            var derived=ParameterTemplates.synchronize(ParameterTemplates.templates(script),existing);
            // Preserve imported/custom metadata defaults until the script definition changes them.
            if(originalTemplates.equals(ParameterTemplates.templates(script))) {
                for(var p:derived) existing.stream().filter(e->p.id.equals(e.id)).findFirst().ifPresent(e->p.defaultValue=e.defaultValue);
            }
            script.parameters=derived;script.revision++;
            ScriptLibrary.getInstance().save(script,template);super.doOKAction();
        } catch(Exception e) { setErrorText(e.getMessage()==null?"配置格式无效":e.getMessage()); }
    }
    @Override public JComponent getPreferredFocusedComponent() { return body; }
}

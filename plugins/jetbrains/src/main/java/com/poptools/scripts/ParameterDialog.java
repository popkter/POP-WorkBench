package com.poptools.scripts;

import com.intellij.openapi.project.Project;
import com.intellij.openapi.ui.*;
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory;
import javax.swing.*;
import java.awt.*;
import java.util.*;
import java.util.List;
import java.util.function.Supplier;

public final class ParameterDialog extends DialogWrapper {
    private final List<ScriptDefinition.Parameter> parameters;
    private final Map<String,String> previous,values=new LinkedHashMap<>();
    private final Map<String,Supplier<String>> readers=new LinkedHashMap<>();
    private final Project project;
    private final String scriptId;
    private final boolean allowSaveDefaults;
    public ParameterDialog(Project project,ScriptDefinition script,Map<String,String> previous) {
        this(project,script,previous,"执行");
    }
    public ParameterDialog(Project project,ScriptDefinition script,Map<String,String> previous,String buttonText) {
        super(project);this.project=project;this.parameters=script.parameters;this.previous=previous;this.scriptId=script.id;
        this.allowSaveDefaults=buttonText.equals("执行");
        setTitle("运行参数 — "+script.title);setOKButtonText(buttonText);init();
    }
    @Override protected JComponent createCenterPanel() {
        JPanel panel=new JPanel(new GridBagLayout());int row=0;
        for(var p:parameters) {
            String initial=previous.getOrDefault(p.id,Objects.toString(p.defaultValue,""));JComponent input;
            switch(p.kind) {
                case "choice" -> {
                    JComboBox<ScriptDefinition.Option> f=new JComboBox<>(p.options.toArray(ScriptDefinition.Option[]::new));
                    p.options.stream().filter(o->o.value.equals(initial)).findFirst().ifPresent(f::setSelectedItem);
                    input=f;readers.put(p.id,()->((ScriptDefinition.Option)f.getSelectedItem()).value);
                }
                case "boolean" -> { JCheckBox f=new JCheckBox();f.setSelected(initial.equalsIgnoreCase("true") || initial.equals("1"));input=f;readers.put(p.id,()->f.isSelected()?"True":"False"); }
                case "file","directory" -> {
                    TextFieldWithBrowseButton f=new TextFieldWithBrowseButton();f.setText(initial);
                    f.addBrowseFolderListener(project,p.kind.equals("file")?FileChooserDescriptorFactory.createSingleFileDescriptor():FileChooserDescriptorFactory.createSingleFolderDescriptor());
                    input=f;readers.put(p.id,f::getText);
                }
                case "multiline" -> { JTextArea f=new JTextArea(initial,5,45);input=new JScrollPane(f);readers.put(p.id,f::getText); }
                case "secret" -> { JPasswordField f=new JPasswordField(initial,40);input=f;readers.put(p.id,()->new String(f.getPassword())); }
                case "android_device" -> {
                    JTextField f=new JTextField(AndroidDevices.selectedSerial(project),40);f.setEditable(false);input=f;readers.put(p.id,f::getText);
                }
                default -> { JTextField f=new JTextField(initial,40);input=f;readers.put(p.id,f::getText); }
            }
            if(allowSaveDefaults && !java.util.Set.of("boolean","choice","android_device").contains(p.kind)) {
                JPanel withDefault=new JPanel(new BorderLayout(4,0));withDefault.add(input);JButton save=new JButton("设为默认值");
                save.addActionListener(e->{try{ScriptLibrary.getInstance().setParameterDefault(scriptId,p.id,readers.get(p.id).get());setErrorText(null);}catch(Exception error){setErrorText(error.getMessage());}});
                withDefault.add(save,BorderLayout.EAST);input=withDefault;
            }
            GridBagConstraints c=new GridBagConstraints();c.gridx=0;c.gridy=row;c.insets=new Insets(5,5,5,5);c.anchor=GridBagConstraints.NORTHWEST;
            panel.add(new JLabel(Objects.toString(p.label,p.id)+(p.required?" *":"")),c);
            c.gridx=1;c.weightx=1;c.fill=GridBagConstraints.HORIZONTAL;panel.add(input,c);row++;
        }
        JScrollPane scroll=new JScrollPane(panel);scroll.setPreferredSize(new Dimension(680,Math.min(550,Math.max(130,row*55))));return scroll;
    }
    @Override protected void doOKAction() {
        try {
            values.clear();for(var p:parameters) {
                String value=readers.get(p.id).get();
                if(p.required && value.isBlank()) throw new IllegalArgumentException("请填写："+p.label);
                if(!value.isBlank() && p.kind.equals("integer")) new java.math.BigInteger(value);
                if(!value.isBlank() && p.kind.equals("number")) new java.math.BigDecimal(value);
                values.put(p.id,value);
            }
            super.doOKAction();
        } catch(Exception e) {setErrorText(e.getMessage()==null?"参数无效":e.getMessage());}
    }
    public Map<String,String> values() {return new LinkedHashMap<>(values);}
}

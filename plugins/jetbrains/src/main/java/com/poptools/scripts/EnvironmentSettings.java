package com.poptools.scripts;

import com.intellij.openapi.options.Configurable;
import com.intellij.openapi.options.ConfigurationException;
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory;
import com.intellij.openapi.ui.TextFieldWithBrowseButton;
import javax.swing.*;
import java.awt.*;
import java.nio.file.*;
import java.util.*;

public final class EnvironmentSettings implements Configurable {
    private JPanel panel;
    private final Map<String,TextFieldWithBrowseButton> fields=new LinkedHashMap<>();
    @Override public String getDisplayName() { return "NicoTools"; }
    @Override public JComponent createComponent() {
        panel=new JPanel(new GridBagLayout()); int row=0;
        for(String name:java.util.List.of("python","powershell","bash","cmd","adb","scrcpy")) {
            GridBagConstraints c=new GridBagConstraints(); c.gridx=0;c.gridy=row;c.anchor=GridBagConstraints.WEST;c.insets=new Insets(5,5,5,5);
            panel.add(new JLabel(name+" 路径"),c);
            TextFieldWithBrowseButton field=new TextFieldWithBrowseButton();
            field.addBrowseFolderListener(null,FileChooserDescriptorFactory.createSingleFileDescriptor());
            fields.put(name,field);c.gridx=1;c.weightx=1;c.fill=GridBagConstraints.HORIZONTAL;panel.add(field,c);row++;
        }
        GridBagConstraints c=new GridBagConstraints();c.gridx=0;c.gridy=row;c.gridwidth=2;c.weighty=1;c.anchor=GridBagConstraints.NORTHWEST;
        panel.add(new JLabel("留空使用系统环境。指定路径无效时直接提示，不自动回退。"),c);
        reset(); return panel;
    }
    @Override public boolean isModified() { return !values().equals(ScriptLibrary.getInstance().paths()); }
    private Map<String,String> values() { Map<String,String> result=new LinkedHashMap<>();fields.forEach((n,f)->{if(!f.getText().isBlank())result.put(n,f.getText().strip());});return result; }
    @Override public void apply() throws ConfigurationException {
        for(var e:values().entrySet()) {
            try { if(!Files.isRegularFile(Path.of(e.getValue()))) throw new ConfigurationException(e.getKey()+" 路径不存在："+e.getValue()); }
            catch(InvalidPathException ex) { throw new ConfigurationException(e.getKey()+" 路径无效"); }
        }
        ScriptLibrary.getInstance().setPaths(values());
    }
    @Override public void reset() { var paths=ScriptLibrary.getInstance().paths();fields.forEach((n,f)->f.setText(paths.getOrDefault(n,""))); }
    @Override public void disposeUIResources() { fields.clear();panel=null; }
}

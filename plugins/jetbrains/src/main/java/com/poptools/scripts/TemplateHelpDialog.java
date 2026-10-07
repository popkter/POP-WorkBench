package com.poptools.scripts;

import com.google.gson.*;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.ui.DialogWrapper;
import com.intellij.openapi.ide.CopyPasteManager;
import javax.swing.*;
import java.awt.*;
import java.awt.datatransfer.StringSelection;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Reuses PopTool's reference snippets, without introducing a user-maintained template library. */
public final class TemplateHelpDialog extends DialogWrapper {
    private record Example(String title,String body,String code) { @Override public String toString(){return title;} }
    private final Project project;
    private final JComboBox<Example> examples=new JComboBox<>();
    private final JTextArea description=new JTextArea(3,65),code=new JTextArea(18,65);
    public TemplateHelpDialog(Project project) {
        super(project);this.project=project;setTitle("脚本模板与参数语法");setOKButtonText("关闭");
        try(var reader=new InputStreamReader(Objects.requireNonNull(getClass().getResourceAsStream("/poptool-guide.json")),StandardCharsets.UTF_8)) {
            for(var section:JsonParser.parseReader(reader).getAsJsonArray()) {
                var o=section.getAsJsonObject();String id=o.get("id").getAsString();if(!id.equals("syntax")&&!id.equals("templates"))continue;
                for(var card:o.getAsJsonArray("cards")){var c=card.getAsJsonObject();if(c.has("code"))examples.addItem(new Example(c.get("title").getAsString(),c.get("body").getAsString(),c.get("code").getAsString()));}
            }
        }catch(Exception error){throw new IllegalStateException("无法读取 PopTool 模板示例",error);}
        description.setEditable(false);description.setLineWrap(true);description.setWrapStyleWord(true);code.setEditable(false);code.setFont(new Font(Font.MONOSPACED,Font.PLAIN,13));
        examples.addActionListener(e->update());update();init();
    }
    private void update(){var example=(Example)examples.getSelectedItem();if(example!=null){description.setText(example.body);code.setText(example.code);code.setCaretPosition(0);}}
    @Override protected JComponent createCenterPanel(){
        JPanel root=new JPanel(new BorderLayout(5,5)),top=new JPanel(new BorderLayout(5,5));top.add(examples,BorderLayout.NORTH);top.add(description);root.add(top,BorderLayout.NORTH);root.add(new JScrollPane(code));
        JPanel buttons=new JPanel(new FlowLayout(FlowLayout.RIGHT));JButton copy=new JButton("复制代码"),preview=new JButton("预览参数替换");
        copy.addActionListener(e->CopyPasteManager.getInstance().setContents(new StringSelection(code.getText())));
        preview.addActionListener(e->{var example=(Example)examples.getSelectedItem();if(example==null)return;
            ScriptDefinition script=new ScriptDefinition();script.title=example.title;script.executor.command=example.code;
            script.parameters=ParameterTemplates.synchronize(java.util.List.of(example.code),java.util.List.of());
            ParameterDialog dialog=new ParameterDialog(project,script,Map.of(),"预览");dialog.setTitle("模板参数预览");
            if(dialog.showAndGet())code.setText(ParameterTemplates.render(example.code,dialog.values()));
        });
        buttons.add(preview);buttons.add(copy);root.add(buttons,BorderLayout.SOUTH);root.setPreferredSize(new Dimension(820,550));return root;
    }
}

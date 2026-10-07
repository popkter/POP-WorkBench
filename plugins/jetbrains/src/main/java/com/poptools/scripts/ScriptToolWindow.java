package com.poptools.scripts;

import com.google.gson.*;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.wm.*;
import com.intellij.openapi.ui.Messages;
import com.intellij.openapi.options.ShowSettingsUtil;
import com.intellij.ui.content.ContentFactory;
import com.intellij.icons.AllIcons;
import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.project.DumbAwareAction;
import com.intellij.ui.ColoredTableCellRenderer;
import com.intellij.ui.SimpleTextAttributes;
import com.intellij.ui.components.JBScrollPane;
import com.intellij.ui.table.JBTable;
import com.intellij.util.ui.JBUI;
import javax.swing.table.AbstractTableModel;
import javax.swing.*;
import java.awt.*;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.List;
import com.intellij.openapi.ide.CopyPasteManager;
import java.awt.datatransfer.StringSelection;
import java.awt.datatransfer.DataFlavor;

public final class ScriptToolWindow implements ToolWindowFactory {
    @Override public void createToolWindowContent(Project project,ToolWindow window) {
        ScriptPanel panel=new ScriptPanel(project);
        window.getContentManager().addContent(ContentFactory.getInstance().createContent(panel,"",false));
    }
    static final class ScriptPanel extends JPanel {
        private final Project project;
        private final List<ScriptDefinition> scripts=new ArrayList<>();
        private final AbstractTableModel model=new AbstractTableModel() {
            private final String[] columns={"名称","类型","说明"};
            @Override public int getRowCount(){return scripts.size();}
            @Override public int getColumnCount(){return columns.length;}
            @Override public String getColumnName(int column){return columns[column];}
            @Override public Object getValueAt(int row,int column){var s=scripts.get(row);return switch(column){case 0->s;case 1->typeLabel(s.executor.kind);default->s.description;};}
            @Override public boolean isCellEditable(int row,int column){return false;}
        };
        final JBTable scriptTable=new JBTable(model);
        final DefaultActionGroup globalActions=new DefaultActionGroup();
        final ActionToolbar toolbar;
        private final JLabel details=new JLabel("双击脚本执行；右键打开脚本操作菜单。");
        ScriptPanel(Project project) {
            super(new BorderLayout());this.project=project;
            scriptTable.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
            scriptTable.setRowSelectionAllowed(true);scriptTable.setColumnSelectionAllowed(false);
            scriptTable.setShowGrid(false);scriptTable.setIntercellSpacing(new Dimension(0,0));
            scriptTable.setRowHeight(JBUI.scale(28));scriptTable.setFillsViewportHeight(true);
            scriptTable.getTableHeader().setReorderingAllowed(false);
            scriptTable.getColumnModel().getColumn(0).setPreferredWidth(JBUI.scale(240));
            scriptTable.getColumnModel().getColumn(1).setPreferredWidth(JBUI.scale(95));
            scriptTable.getColumnModel().getColumn(1).setMaxWidth(JBUI.scale(120));
            scriptTable.getColumnModel().getColumn(2).setPreferredWidth(JBUI.scale(240));
            scriptTable.setDefaultRenderer(Object.class,new ColoredTableCellRenderer() {
                @Override protected void customizeCellRenderer(JTable table,Object value,boolean selected,boolean focused,int row,int column) {
                    setBorder(JBUI.Borders.empty(0,8));
                    if(selected){setOpaque(true);setBackground(table.getSelectionBackground());}
                    if(value instanceof ScriptDefinition script){setIcon(AllIcons.Nodes.Console);append(script.title,SimpleTextAttributes.REGULAR_ATTRIBUTES);setToolTipText(script.description.isBlank()?script.title:script.description);}
                    else{append(Objects.toString(value,""),selected?SimpleTextAttributes.REGULAR_ATTRIBUTES:SimpleTextAttributes.GRAYED_ATTRIBUTES);setToolTipText(Objects.toString(value,""));}
                }
            });
            scriptTable.getEmptyText().setText("暂无脚本，点击工具栏“新建脚本”或“导入”");
            globalActions.add(action("新建脚本","新建自定义脚本",AllIcons.Actions.AddFile,()->edit(new ScriptDefinition(),false)));
            globalActions.add(action("批量操作","批量导入或导出脚本目录",AllIcons.Actions.SyncPanels,this::directoryTransfer));
            globalActions.add(action("导入","从剪贴板导入脚本",AllIcons.Actions.Download,this::importClipboard));
            globalActions.add(action("环境路径","配置解释器和工具路径",AllIcons.General.Settings,()->ShowSettingsUtil.getInstance().showSettingsDialog(project,EnvironmentSettings.class)));
            toolbar=ActionManager.getInstance().createActionToolbar("NicoTools.ScriptToolbar",globalActions,true);
            toolbar.setTargetComponent(scriptTable);
            details.setBorder(JBUI.Borders.empty(6,8));
            add(toolbar.getComponent(),BorderLayout.NORTH);add(new JBScrollPane(scriptTable),BorderLayout.CENTER);add(details,BorderLayout.SOUTH);
            ScriptLibrary.getInstance().listen(this::refresh,project);refresh();
            scriptTable.getSelectionModel().addListSelectionListener(e->{var s=selected();details.setText(s==null?"双击脚本执行；右键打开脚本操作菜单。":s.description.isBlank()?typeLabel(s.executor.kind):s.description);});
            scriptTable.addMouseListener(new MouseAdapter() {
                private void popup(MouseEvent event) {
                    if(!event.isPopupTrigger())return;
                    ScriptDefinition script=scriptAt(event.getPoint());if(script==null)return;
                    createScriptMenu(script).getComponent().show(scriptTable,event.getX(),event.getY());
                }
                @Override public void mousePressed(MouseEvent event){popup(event);}
                @Override public void mouseReleased(MouseEvent event){popup(event);}
                @Override public void mouseClicked(MouseEvent event){
                    if(SwingUtilities.isLeftMouseButton(event) && event.getClickCount()==2) {
                        ScriptDefinition script=scriptAt(event.getPoint());
                        if(script!=null)ScriptRunner.run(project,script,Map.of());
                    }
                }
            });
            scriptTable.getInputMap().put(KeyStroke.getKeyStroke("shift F10"),"nicoTools.popup");
            scriptTable.getInputMap().put(KeyStroke.getKeyStroke("CONTEXT_MENU"),"nicoTools.popup");
            scriptTable.getActionMap().put("nicoTools.popup",new AbstractAction(){@Override public void actionPerformed(java.awt.event.ActionEvent e){
                ScriptDefinition script=selected();if(script==null)return;
                Rectangle row=scriptTable.getCellRect(scriptTable.getSelectedRow(),0,true);
                createScriptMenu(script).getComponent().show(scriptTable,row.x+JBUI.scale(24),row.y+row.height);
            }});
        }
        private static String typeLabel(String kind){return switch(kind){case "powershell"->"PowerShell";case "python"->"Python";case "bash"->"Bash";case "batch"->"BAT";default->"外部进程";};}
        ScriptDefinition scriptAt(Point point) {
            int index=scriptTable.rowAtPoint(point);
            if(index<0)return null;
            if(point.x<0 || point.x>=scriptTable.getWidth())return null;
            scriptTable.requestFocusInWindow();scriptTable.setRowSelectionInterval(index,index);return scripts.get(scriptTable.convertRowIndexToModel(index));
        }
        ActionPopupMenu createScriptMenu(ScriptDefinition script) {
            DefaultActionGroup group=new DefaultActionGroup();
            group.add(action("执行脚本","执行所选脚本",AllIcons.Actions.Execute,()->ScriptRunner.run(project,script,Map.of())));
            group.add(action("编辑脚本","编辑所选脚本",AllIcons.Actions.Edit,()->edit(script,false)));
            group.add(action("分享脚本","复制分享内容到剪贴板",AllIcons.Actions.Share,()->shareClipboard(script)));
            group.addSeparator();
            group.add(action("删除脚本","删除所选脚本",AllIcons.Actions.GC,()->{
                if(Messages.showYesNoDialog(project,"删除“"+script.title+"”？","确认删除",Messages.getQuestionIcon())==Messages.YES)
                    ScriptLibrary.getInstance().delete(script.id,false);
            }));
            ActionPopupMenu menu=ActionManager.getInstance().createActionPopupMenu("NicoTools.ScriptPopup",group);
            menu.setTargetComponent(scriptTable);
            return menu;
        }
        private AnAction action(String title,String description,Icon icon,Runnable run){return new DumbAwareAction(title,description,icon){
            @Override public void actionPerformed(AnActionEvent e){run.run();}
            @Override public void update(AnActionEvent e){e.getPresentation().setEnabled(!project.isDisposed());}
            @Override public ActionUpdateThread getActionUpdateThread(){return ActionUpdateThread.EDT;}
        };}
        private ScriptDefinition selected() {int row=scriptTable.getSelectedRow();return row<0 || row>=scripts.size()?null:scripts.get(scriptTable.convertRowIndexToModel(row));}
        private void edit(ScriptDefinition s,boolean template) {new ScriptEditor(project,s,template).show();}
        private void refresh() {
            ScriptDefinition selected=selected();String sid=selected==null?null:selected.id;
            scriptTable.clearSelection();scripts.clear();scripts.addAll(ScriptLibrary.getInstance().list(false));model.fireTableDataChanged();
            for(int i=0;i<scripts.size();i++)if(scripts.get(i).id.equals(sid))scriptTable.setRowSelectionInterval(i,i);
        }
        private void importClipboard() {
            try {Object content=CopyPasteManager.getInstance().getContents(DataFlavor.stringFlavor);if(!(content instanceof String text))throw new IllegalArgumentException("剪贴板没有脚本 JSON");importJson(text);}
            catch(Exception e){Messages.showErrorDialog(project,Objects.toString(e.getMessage(),e.toString()),"导入失败");}
        }
        private void importJson(String text) {
            importJson(text,null);
        }
        private void importJson(String text,Path sourceDirectory) {
            JsonElement root=JsonParser.parseString(text);List<JsonElement> entries=new ArrayList<>();
            if(root.isJsonArray())root.getAsJsonArray().forEach(entries::add);
            else if(root.isJsonObject() && root.getAsJsonObject().has("scripts"))root.getAsJsonObject().getAsJsonArray("scripts").forEach(entries::add);
            else entries.add(root);
            boolean template=false;int success=0,skipped=0;List<String> errors=new ArrayList<>();
            for(int index=0;index<entries.size();index++) {
                try {
                    ScriptDefinition s=ScriptJson.decode(entries.get(index));
                    String incomingId=s.id,incomingTitle=s.title;
                    ScriptDefinition conflict=ScriptLibrary.getInstance().list(template).stream().filter(old->old.id.equals(incomingId)||old.title.equals(incomingTitle)).findFirst().orElse(null);
                    if(conflict!=null) {
                        int answer=Messages.showDialog(project,"“"+s.title+"”已存在，请选择处理方式。","导入冲突",new String[]{"覆盖","另存","跳过"},2,Messages.getQuestionIcon());
                        if(answer==0)s.id=conflict.id;
                        else if(answer==1){s.id=new ScriptDefinition().id;s.title=uniqueTitle(s.title,template);}
                        else {skipped++;continue;}
                    }
                    if(sourceDirectory!=null)s=ScriptDirectoryTransfer.prepare(s,sourceDirectory,Path.of(com.intellij.openapi.application.PathManager.getConfigPath(),"poptool-assets"));
                    ScriptLibrary.getInstance().save(s,template);success++;
                } catch(Exception e){errors.add("第 "+(index+1)+" 项："+Objects.toString(e.getMessage(),"数据格式错误"));}
            }
            Messages.showInfoMessage(project,"成功 "+success+"，跳过 "+skipped+"，失败 "+errors.size()+"\n"+String.join("\n",errors),"导入结果");
        }
        private String uniqueTitle(String title,boolean template) {
            Set<String> used=new HashSet<>();ScriptLibrary.getInstance().list(template).forEach(s->used.add(s.title));int suffix=2;
            String candidate=title+" ("+suffix+")";while(used.contains(candidate))candidate=title+" ("+(++suffix)+")";return candidate;
        }
        private void shareClipboard(ScriptDefinition s) {
            try {
                CopyPasteManager.getInstance().setContents(new StringSelection(ScriptJson.share(s)));
                Messages.showInfoMessage(project,"脚本已复制到剪贴板，默认值已去除。","分享脚本");
            }catch(Exception e){Messages.showErrorDialog(project,e.toString(),"导出失败");}
        }
        private void directoryTransfer() {
            int action=Messages.showDialog(project,"批量导入或导出脚本目录。","批量操作",new String[]{"导入目录","导出目录","取消"},2,Messages.getQuestionIcon());
            if(action!=0 && action!=1)return;
            JFileChooser chooser=new JFileChooser();chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY);
            if(chooser.showOpenDialog(this)!=JFileChooser.APPROVE_OPTION)return;
            Path directory=chooser.getSelectedFile().toPath();
            try {
                if(action==0) {
                    JsonArray data=new JsonArray();List<String> invalid=new ArrayList<>();
                    Path tools=Files.isDirectory(directory.resolve("tools"))?directory.resolve("tools"):directory;
                    try(var files=Files.walk(tools)) {
                        for(Path file:files.filter(p->Files.isRegularFile(p)&&p.toString().endsWith(".json")).toList()) {
                            try{JsonElement json=JsonParser.parseString(Files.readString(file,StandardCharsets.UTF_8));if(json.isJsonArray())json.getAsJsonArray().forEach(data::add);else data.add(json);}
                            catch(Exception e){invalid.add(file.getFileName()+"："+e.getMessage());}
                        }
                    }
                    if(data.isEmpty() && invalid.isEmpty())throw new IllegalArgumentException("目录中没有脚本 JSON");
                    // Back up the current library before any incoming definitions are applied.
                    Path backup=Path.of(com.intellij.openapi.application.PathManager.getConfigPath(),"poptool-backups",Long.toString(System.currentTimeMillis()));
                    writeDirectory(backup,ScriptLibrary.getInstance().list(false));
                    importJson(data.toString(),directory);
                    if(!invalid.isEmpty())Messages.showErrorDialog(project,String.join("\n",invalid),"无法读取的脚本文件");
                } else {
                    Path destination=directory.resolve("poptool-scripts-"+System.currentTimeMillis());writeDirectory(destination,ScriptLibrary.getInstance().list(false));
                    Messages.showInfoMessage(project,"已导出到："+destination,"导出脚本目录");
                }
            }catch(Exception e){Messages.showErrorDialog(project,Objects.toString(e.getMessage(),e.toString()),"批量操作失败");}
        }
        private static void writeDirectory(Path directory,List<ScriptDefinition> scripts) throws Exception {
            ScriptDirectoryTransfer.writeDirectory(directory,scripts);
        }
    }
}

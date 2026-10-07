package com.poptools.scripts;

import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.project.*;
import com.intellij.terminal.JBTerminalWidget;
import org.jetbrains.plugins.terminal.block.util.TerminalDataContextUtils;
import com.intellij.terminal.frontend.view.TerminalView;
import com.intellij.terminal.frontend.view.TerminalViewKt;

public final class NewFromTerminalAction extends DumbAwareAction {
    static String selection(AnActionEvent e) {
        TerminalView view=e.getData(TerminalView.Companion.getDATA_KEY());
        if(view!=null) {
            var selected=view.getTextSelectionModel().getSelection();
            if(selected!=null)return TerminalViewKt.activeOutputModel(view).getText(selected.getStartOffset(),selected.getEndOffset()).toString();
            return null;
        }
        String text=e.getData(JBTerminalWidget.SELECTED_TEXT_DATA_KEY);if(text!=null)return text;
        var editor=TerminalDataContextUtils.INSTANCE.getTerminalEditor(e);
        if(editor==null)editor=e.getData(CommonDataKeys.EDITOR);
        return editor==null?null:editor.getSelectionModel().getSelectedText();
    }
    @Override public void actionPerformed(AnActionEvent e) {
        String text=selection(e);if(e.getProject()!=null && text!=null && !text.isEmpty())open(e.getProject(),text);
    }
    static void open(Project project,String text){
        ScriptDefinition s=new ScriptDefinition();s.executor.command=text;new ScriptEditor(project,s,false).show();
    }
    @Override public void update(AnActionEvent e){String text=selection(e);e.getPresentation().setEnabled(e.getProject()!=null && text!=null && !text.isEmpty());}
    @Override public ActionUpdateThread getActionUpdateThread(){return ActionUpdateThread.EDT;}
}

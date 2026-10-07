package com.poptools.scripts;
import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.project.DumbAwareAction;
import com.intellij.openapi.wm.ToolWindowManager;

public final class ManageScriptsAction extends DumbAwareAction {
    @Override public void actionPerformed(AnActionEvent e) {
        if(e.getProject()==null)return;
        var window=ToolWindowManager.getInstance(e.getProject()).getToolWindow("NicoTools");if(window!=null)window.show();
    }
    @Override public void update(AnActionEvent e) {e.getPresentation().setEnabled(e.getProject()!=null);}
    @Override public ActionUpdateThread getActionUpdateThread(){return ActionUpdateThread.BGT;}
}

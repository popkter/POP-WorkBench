package com.poptools.scripts;

import com.intellij.openapi.startup.StartupActivity;
import com.intellij.openapi.project.Project;
import com.intellij.terminal.JBTerminalWidget;
import com.intellij.terminal.ui.TerminalWidget;
import com.jediterm.terminal.ui.*;
import org.jetbrains.plugins.terminal.TerminalToolWindowManager;
import javax.swing.*;
import java.util.*;

/** Classic terminal builds its own action chain rather than an XML menu group. */
public final class TerminalIntegration implements StartupActivity.DumbAware {
    @Override public void runActivity(Project project){
        var manager=TerminalToolWindowManager.getInstance(project);
        Set<TerminalWidget> registered=Collections.newSetFromMap(new WeakHashMap<>());
        java.util.function.Consumer<TerminalWidget> install=widget->{
            if(!registered.add(widget))return;
            JBTerminalWidget classic=JBTerminalWidget.asJediTermWidget(widget);if(classic==null)return;
            TerminalActionProvider old=classic.getNextProvider();
            classic.setNextProvider(new TerminalActionProvider(){
                private TerminalActionProvider next=old;
                @Override public List<TerminalAction> getActions(){return List.of(new TerminalAction(
                    new TerminalActionPresentation("新建 NicoTools 自定义脚本",List.<KeyStroke>of()),event->{
                        String text=classic.getSelectedText();if(text!=null && !text.isEmpty())NewFromTerminalAction.open(project,text);return true;
                    }).withEnabledSupplier(()->{String text=classic.getSelectedText();return text!=null && !text.isEmpty();}).separatorBefore(true));}
                @Override public TerminalActionProvider getNextProvider(){return next;}
                @Override public void setNextProvider(TerminalActionProvider provider){next=provider;}
            });
            com.intellij.openapi.util.Disposer.register(project,()->classic.setNextProvider(old));
        };
        manager.addNewTerminalSetupHandler(install,project);manager.getTerminalWidgets().forEach(install);
    }
}

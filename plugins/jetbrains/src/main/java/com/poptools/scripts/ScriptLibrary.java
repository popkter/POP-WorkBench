package com.poptools.scripts;

import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.components.*;
import com.intellij.openapi.Disposable;
import com.intellij.openapi.util.Disposer;
import java.util.*;
import java.util.concurrent.CopyOnWriteArrayList;

@State(name="PopToolScriptLibrary",storages=@Storage("poptool-scripts.xml"))
public final class ScriptLibrary implements PersistentStateComponent<ScriptLibrary.State> {
    public static final class State {
        public List<String> scripts=new ArrayList<>();
        public Map<String,String> paths=new LinkedHashMap<>();
    }
    private State state=new State();
    private final List<Runnable> listeners=new CopyOnWriteArrayList<>();
    public static ScriptLibrary getInstance() { return ApplicationManager.getApplication().getService(ScriptLibrary.class); }
    @Override public State getState() {
        State snapshot=new State();snapshot.scripts=new ArrayList<>(state.scripts);snapshot.paths=new LinkedHashMap<>(state.paths);return snapshot;
    }
    @Override public void loadState(State value) { state=value; }
    public List<ScriptDefinition> list(boolean ignored) {
        return state.scripts.stream().map(s->ScriptJson.GSON.fromJson(s,ScriptDefinition.class)).toList();
    }
    public void save(ScriptDefinition script,boolean template) {
        ScriptJson.validate(script);
        List<String> entries=state.scripts;
        entries.removeIf(s->ScriptJson.GSON.fromJson(s,ScriptDefinition.class).id.equals(script.id));
        entries.add(ScriptJson.GSON.toJson(script)); changed();
    }
    public void delete(String id,boolean template) {
        state.scripts.removeIf(s->ScriptJson.GSON.fromJson(s,ScriptDefinition.class).id.equals(id)); changed();
    }
    public Map<String,String> paths() { return new LinkedHashMap<>(state.paths); }
    public void setPaths(Map<String,String> paths) { state.paths=new LinkedHashMap<>(paths); }
    public void setParameterDefault(String scriptId,String parameterId,String value) {
        ScriptDefinition script=list(false).stream().filter(s->s.id.equals(scriptId)).findFirst().orElseThrow(()->new IllegalArgumentException("请先保存脚本"));
        for(var parameter:script.parameters)if(parameter.id.equals(parameterId)){parameter.defaultValue=value;script.revision++;save(script,false);return;}
        throw new IllegalArgumentException("参数不存在");
    }
    public void listen(Runnable listener,Disposable owner) {
        listeners.add(listener); Disposer.register(owner,()->listeners.remove(listener));
    }
    private void changed() { listeners.forEach(Runnable::run); }
}

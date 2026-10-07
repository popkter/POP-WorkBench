package com.poptools.scripts;

import com.google.gson.*;
import java.util.*;

public final class ScriptJson {
    // Field naming keeps the original PopTool "default" property.
    public static final Gson GSON=new GsonBuilder().setPrettyPrinting().disableHtmlEscaping()
        .setObjectToNumberStrategy(ToNumberPolicy.LONG_OR_DOUBLE)
        .setFieldNamingStrategy(f -> f.getName().equals("defaultValue")?"default":f.getName())
        .registerTypeAdapter(ScriptDefinition.Option.class,(JsonDeserializer<ScriptDefinition.Option>)(json,type,ctx)->{
            if(json.isJsonPrimitive()) return new ScriptDefinition.Option(json.getAsString(),json.getAsString());
            JsonObject o=json.getAsJsonObject(); return new ScriptDefinition.Option(o.get("label").getAsString(),o.get("value").getAsString());
        }).create();
    private static final Set<String> KINDS=Set.of("powershell","python","bash","batch","process");
    private static final Set<String> PARAMETER_KINDS=Set.of("text","multiline","integer","number","boolean","choice","file","directory","android_device","secret");
    private ScriptJson() {}
    public static ScriptDefinition copy(ScriptDefinition s) { return GSON.fromJson(GSON.toJson(s),ScriptDefinition.class); }
    public static ScriptDefinition.Parameter copyParameter(ScriptDefinition.Parameter p) { return GSON.fromJson(GSON.toJson(p),ScriptDefinition.Parameter.class); }
    public static void validate(ScriptDefinition s) {
        if(s==null || s.schema_version!=1 || s.executor==null || s.title==null || s.title.isBlank() || s.executor.command==null || s.executor.command.isBlank())
            throw new IllegalArgumentException("脚本名称、正文为空或数据版本不支持");
        if(!KINDS.contains(s.executor.kind)) throw new IllegalArgumentException("不支持的执行类型："+s.executor.kind);
        if(s.executor.args==null || s.executor.env==null || s.executor.requirements==null || s.parameters==null || s.presentation==null)
            throw new IllegalArgumentException("脚本字段不完整");
        if(!Set.of("auto","use","none").contains(s.executor.android_device_mode)) throw new IllegalArgumentException("无效的设备模式");
        java.nio.charset.Charset.forName(s.executor.encoding);
        if(s.executor.timeout_seconds!=null && s.executor.timeout_seconds<1) throw new IllegalArgumentException("超时必须大于零");
        Set<String> ids=new HashSet<>();
        for(var p:s.parameters) {
            if(p.id==null || !ids.add(p.id) || !PARAMETER_KINDS.contains(p.kind) || p.options==null) throw new IllegalArgumentException("不支持或重复的参数："+p.id);
            if(p.id.isBlank() || !p.id.codePoints().allMatch(c->c=='_' || Character.isLetterOrDigit(c))) throw new IllegalArgumentException("无效参数名称："+p.id);
            if(p.kind.equals("choice") && p.options.isEmpty()) throw new IllegalArgumentException("选择参数没有选项："+p.id);
        }
        // Validate templates without discarding imported parameter metadata/defaults.
        ParameterTemplates.synchronize(ParameterTemplates.templates(s),s.parameters);
    }
    public static ScriptDefinition decode(JsonElement element) {
        JsonObject o=element.getAsJsonObject();
        if(o.has("format")) {
            if(!o.get("format").getAsString().equals("poptools.custom-script") || !o.has("format_version") || o.get("format_version").getAsInt()!=1)
                throw new IllegalArgumentException("不支持的 PopTool 分享格式版本");
            o=o.getAsJsonObject("tool");
        }
        if(o.has("section") && !Set.of("custom","local").contains(o.get("section").getAsString())) throw new IllegalArgumentException("只能导入自定义脚本");
        checkFields(o,Set.of("schema_version","id","revision","origin","section","title","description","tags","editable","enabled","executor","parameters","presentation","interpreter"),"脚本");
        if(o.has("executor")) checkFields(o.getAsJsonObject("executor"),Set.of("kind","command","args","cwd","timeout_seconds","encoding","env","requirements","android_device_mode"),"执行配置");
        if(o.has("presentation"))checkFields(o.getAsJsonObject("presentation"),Set.of("icon","order","confirm_before_run","output_mode"),"展示配置");
        if(o.has("parameters"))for(var p:o.getAsJsonArray("parameters"))checkFields(p.getAsJsonObject(),Set.of("id","label","kind","required","default","placeholder","options"),"参数");
        ScriptDefinition s=GSON.fromJson(o,ScriptDefinition.class); validate(s);
        var derived=ParameterTemplates.synchronize(ParameterTemplates.templates(s),s.parameters);
        for(var p:derived)if(s.parameters.stream().noneMatch(old->old.id.equals(p.id)))s.parameters.add(p);
        s.origin="custom"; s.section="custom"; s.editable=true; s.enabled=true; return s;
    }
    private static void checkFields(JsonObject object,Set<String> supported,String label) {
        for(String key:object.keySet())if(!supported.contains(key))throw new IllegalArgumentException(label+"包含不支持的字段："+key);
    }
    public static String share(ScriptDefinition script) {
        JsonObject tool=GSON.toJsonTree(script).getAsJsonObject();tool.remove("interpreter");
        for(var p:tool.getAsJsonArray("parameters"))p.getAsJsonObject().remove("default");
        var executor=tool.getAsJsonObject("executor");
        executor.addProperty("command",ParameterTemplates.stripDefaults(executor.get("command").getAsString()));
        JsonArray args=new JsonArray();executor.getAsJsonArray("args").forEach(a->args.add(ParameterTemplates.stripDefaults(a.getAsString())));executor.add("args",args);
        JsonObject env=new JsonObject();executor.getAsJsonObject("env").entrySet().forEach(e->env.addProperty(e.getKey(),ParameterTemplates.stripDefaults(e.getValue().getAsString())));executor.add("env",env);
        if(executor.has("cwd")&&!executor.get("cwd").isJsonNull())executor.addProperty("cwd",ParameterTemplates.stripDefaults(executor.get("cwd").getAsString()));
        JsonObject payload=new JsonObject();payload.addProperty("format","poptools.custom-script");payload.addProperty("format_version",1);payload.add("tool",tool);return GSON.toJson(payload);
    }
}

package com.poptools.scripts;

import java.nio.file.*;
import java.util.*;

public final class CoreTests {
    private static int checks;
    static void check(boolean value,String label){if(!value)throw new AssertionError(label);checks++;}
    static void fails(Runnable action,String label){try{action.run();throw new AssertionError(label);}catch(IllegalArgumentException expected){checks++;}}
    public static void main(String[] args) throws Exception {
        String source="Var logs = ${日志目录@dir:C:/private}\npVal mode = ${模式:开启=1|关闭=0}\necho \"${logs}\" ${mode} ${旧格式=hello} ${文件@file}";
        var parameters=ParameterTemplates.synchronize(List.of(source),List.of());
        check(parameters.size()==4,"declaration order and deduplication");
        check(parameters.get(0).id.equals("logs") && parameters.get(0).label.equals("日志目录") && parameters.get(0).kind.equals("directory"),"declaration identity/label/type");
        check(parameters.get(1).options.get(1).value.equals("0"),"choice actual values");
        check(ParameterTemplates.render(source,Map.of("logs","D:/中文 空格","mode","0","文件","a\"b\\c")).equals("echo \"D:/中文 空格\" 0 hello a\"b\\c"),"literal substitution and declaration removal");
        check(ParameterTemplates.render("${文本}",Map.of("文本","一\n二$\\")).equals("一\n二$\\"),"multiline dollar and backslash");
        check(ParameterTemplates.synchronize(List.of("${on=1|off=0}"),List.of()).getFirst().kind.equals("choice"),"legacy choices");
        var booleanParameter=new ScriptDefinition.Parameter();booleanParameter.id="flag";booleanParameter.kind="boolean";
        check(ParameterTemplates.renderArguments(List.of("?flag:--enabled","${x}"),Map.of("flag","False","x","中文 空格"),List.of(booleanParameter)).equals(List.of("中文 空格")),"conditional argument false omitted");
        check(ParameterTemplates.renderArguments(List.of("?flag:--enabled",""),Map.of("flag","True"),List.of(booleanParameter)).equals(List.of("--enabled","")),"conditional argument true and empty argument preserved");
        fails(()->ParameterTemplates.synchronize(List.of("${a:1} ${a:2}"),List.of()),"conflicting defaults");
        fails(()->ParameterTemplates.synchronize(List.of("${a@bad}"),List.of()),"unsupported kind");
        fails(()->ParameterTemplates.synchronize(List.of("Var a = ${名:1}\nVar a = ${名:2}\n${a}"),List.of()),"conflicting declarations");
        ScriptDefinition s=new ScriptDefinition();s.title="迁移测试";s.executor.command=source;s.parameters=parameters;s.executor.env.put("TEST","${logs}");
        var decoded=ScriptJson.decode(com.google.gson.JsonParser.parseString(ScriptJson.GSON.toJson(s)));
        check(decoded.parameters.getFirst().defaultValue.equals("C:/private"),"default metadata round trip");
        check(decoded.executor.env.get("TEST").equals("${logs}"),"environment round trip");
        check(ScriptJson.copy(s).parameters.get(1).options.size()==2,"choice object round trip");
        var numeric=new ScriptDefinition.Parameter();numeric.id="n";numeric.defaultValue=12L;s.parameters.add(numeric);
        check(ScriptJson.copy(s).parameters.getLast().defaultValue.toString().equals("12"),"integer metadata does not become decimal");
        String shared="{\"format\":\"poptools.custom-script\",\"format_version\":1,\"tool\":"+ScriptJson.GSON.toJson(s)+"}";
        check(ScriptJson.decode(com.google.gson.JsonParser.parseString(shared)).title.equals(s.title),"PopTool transfer envelope");
        String sanitized=ScriptJson.share(s);
        check(!sanitized.contains("C:/private")&&!sanitized.contains("\"default\"")&&!sanitized.contains("interpreter"),"sharing strips private defaults and plugin-only metadata");
        check(sanitized.contains("模式:开启=1|关闭=0"),"sharing retains choice definitions");
        fails(()->ScriptJson.decode(com.google.gson.JsonParser.parseString(shared.replace("format_version\":1","format_version\":9"))),"future format rejection");
        Path temp=Files.createTempDirectory("poptool-resolver-test");
        try {
            Path fake=Files.writeString(temp.resolve("adb.exe"),"");
            var resolver=new EnvironmentResolver(Map.of(),Map.of("Path",temp.toString()));
            check(resolver.resolve("adb","").equals(fake),"case-insensitive system PATH");
            fails(()->resolver.resolve("python",temp.resolve("missing.exe").toString()),"explicit path does not fall back");
            var settings=new EnvironmentResolver(Map.of("adb",fake.toString(),"scrcpy",temp.resolve("missing.exe").toString()),Map.of("PATH",""));
            check(settings.executionEnvironment(List.of()).get("POPTOOLS_ADB").equals(fake.toString()),"configured tool path injection and irrelevant dependency tolerance");
            fails(()->settings.executionEnvironment(List.of("scrcpy")),"required dependency error");
        } finally {Files.deleteIfExists(temp.resolve("adb.exe"));Files.delete(temp);}
        s.executor.command="adb devices";check(!AndroidDevices.needed(s),"non-device command");
        s.executor.command="adb shell getprop";check(AndroidDevices.needed(s),"adb device command");
        s.executor.android_device_mode="none";check(!AndroidDevices.needed(s),"explicit no-device mode");
        s.executor.command="print('hello')";s.executor.android_device_mode="auto";check(!AndroidDevices.needed(s),"ordinary script no device");
        s.executor.requirements.add("android_device");check(AndroidDevices.needed(s),"PopTool android_device requirement preserved");
        com.android.ddmlib.IDevice online=device("selected-serial",true);
        check(AndroidDevices.serialFromSelectedDevices(List.of(online)).equals("selected-serial"),"selected device serial used unchanged");
        fails(()->AndroidDevices.serialFromSelectedDevices(List.of()),"missing selection rejected");
        fails(()->AndroidDevices.serialFromSelectedDevices(List.of(online,device("other",true))),"multiple selected devices rejected");
        fails(()->AndroidDevices.serialFromSelectedDevices(List.of(device("offline",false))),"offline selected device rejected without fallback");
        fails(()->AndroidDevices.serialFromSelectedDevices(Arrays.asList((com.android.ddmlib.IDevice)null)),"uninitialized selected device rejected");
        Path migration=Files.createTempDirectory("poptool-migration-test");
        try{
            Path exported=migration.resolve("export"),assets=migration.resolve("assets");Files.createDirectories(exported.resolve("scripts"));
            Files.writeString(exported.resolve("scripts/main.py"),"import helper; print(helper.VALUE)");Files.writeString(exported.resolve("scripts/helper.py"),"VALUE = 'preserved'");
            ScriptDefinition referenced=new ScriptDefinition();referenced.executor.kind="python";referenced.executor.command="scripts/main.py --arg";
            var migrated=ScriptDirectoryTransfer.prepare(referenced,exported,assets);
            check(migrated.executor.command.endsWith("main.py\" --arg"),"directory import rebases file while preserving arguments");
            try(var files=Files.walk(assets)){check(files.anyMatch(p->p.getFileName().toString().equals("helper.py")),"directory import keeps sibling Python dependencies");}
            check(referenced.executor.command.equals("scripts/main.py --arg"),"directory import does not mutate source definition");
            Path backup=migration.resolve("backup");
            ScriptDirectoryTransfer.writeDirectory(backup,List.of(migrated));
            ScriptDefinition restored;
            try(var definitions=Files.list(backup.resolve("tools"))){restored=ScriptJson.decode(com.google.gson.JsonParser.parseString(Files.readString(definitions.findFirst().orElseThrow())));}
            check(!restored.executor.command.contains(assets.toString().replace('\\','/')) && restored.executor.command.startsWith("\"scripts/"),"export uses portable relative entry");
            var importedAgain=ScriptDirectoryTransfer.prepare(restored,backup,migration.resolve("restored-assets"));
            check(importedAgain.executor.command.endsWith("main.py\" --arg"),"export/import round trip keeps entry and arguments");
            try(var files=Files.walk(migration.resolve("restored-assets"))){check(files.anyMatch(p->p.getFileName().toString().equals("helper.py")),"export/import round trip preserves sibling dependencies");}
            check(migrated.executor.command.contains(assets.toString().replace('\\','/')),"export does not mutate installed script");
        }finally{try(var files=Files.walk(migration)){for(Path p:files.sorted(Comparator.reverseOrder()).toList())Files.delete(p);}}
        if(args.length>0)checkOracle(Path.of(args[0]));
        System.out.println("Passed "+checks+" core checks.");
    }
    private static com.android.ddmlib.IDevice device(String serial,boolean online) {
        return (com.android.ddmlib.IDevice)java.lang.reflect.Proxy.newProxyInstance(CoreTests.class.getClassLoader(),new Class[]{com.android.ddmlib.IDevice.class},(proxy,method,args)->switch(method.getName()){
            case "getSerialNumber"->serial;case "isOnline"->online;case "getState"->com.android.ddmlib.IDevice.DeviceState.OFFLINE;default->throw new UnsupportedOperationException(method.getName());
        });
    }
    private static void checkOracle(Path fixture) throws Exception {
        var rows=com.google.gson.JsonParser.parseString(Files.readString(fixture)).getAsJsonArray();
        for(var row:rows) {
            var o=row.getAsJsonObject();String template=o.get("template").getAsString();
            if(o.has("error")){fails(()->ParameterTemplates.synchronize(List.of(template),List.of()),"PopTool rejects "+template);continue;}
            List<ScriptDefinition.Parameter> existing=o.has("existing")?Arrays.asList(ScriptJson.GSON.fromJson(o.get("existing"),ScriptDefinition.Parameter[].class)):List.of();
            var actual=ParameterTemplates.synchronize(List.of(template),existing);
            var expected=Arrays.asList(ScriptJson.GSON.fromJson(o.get("parameters"),ScriptDefinition.Parameter[].class));
            check(actual.size()==expected.size(),"PopTool parameter count "+template);
            for(int i=0;i<actual.size();i++) {
                var a=actual.get(i);var e=expected.get(i);
                check(Objects.equals(a.id,e.id)&&Objects.equals(a.label,e.label)&&Objects.equals(a.kind,e.kind)&&Objects.equals(a.defaultValue,e.defaultValue)&&a.required==e.required&&a.options.equals(e.options),"PopTool parameter semantics "+template);
            }
            Map<String,String> values=new LinkedHashMap<>();o.getAsJsonObject("values").entrySet().forEach(e->values.put(e.getKey(),e.getValue().getAsString()));
            check(ParameterTemplates.render(template,values).equals(o.get("rendered").getAsString()),"PopTool rendered text "+template);
        }
    }
}

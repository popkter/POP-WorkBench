package com.poptools.scripts;

import java.nio.file.*;
import java.util.*;

public final class EnvironmentResolver {
    private final Map<String,String> paths;
    private final Map<String,String> environment;
    public EnvironmentResolver(Map<String,String> paths,Map<String,String> environment) {this.paths=paths;this.environment=environment;}
    public Path resolve(String name,String override) {
        String configured=override==null || override.isBlank()?paths.getOrDefault(name,""):override;
        if(!configured.isBlank()) {
            Path path=Path.of(configured);
            if(!path.isAbsolute() || !Files.isRegularFile(path)) throw new IllegalArgumentException(name+" 配置路径不存在或不是绝对文件路径："+configured+"。请在 NicoTools 设置中修改。");
            if(name.equals("bash") && isWslBash(path))throw new IllegalArgumentException("首版不支持 WSL Bash，请指定 Windows 本机 Bash（例如 Git Bash）路径。");
            return path;
        }
        List<String> names=name.equals("powershell")?List.of("pwsh","powershell"):name.equals("python")?List.of("python","python3"):List.of(name);
        String pathValue=environment.entrySet().stream().filter(e->e.getKey().equalsIgnoreCase("PATH")).map(Map.Entry::getValue).findFirst().orElse("");
        for(String candidate:names) {
            Path explicit=Path.of(candidate);
            if(explicit.isAbsolute() && Files.isRegularFile(explicit)) return explicit;
            if(explicit.isAbsolute()) continue;
            for(String dir:pathValue.split(java.io.File.pathSeparator)) {
                if(dir.isBlank())continue;
                for(String extension:List.of("",".exe",".cmd",".bat")) {
                    try {Path found=Path.of(dir.replace("\"",""),candidate+extension);if(Files.isRegularFile(found) && !(name.equals("bash") && isWslBash(found)))return found.toAbsolutePath();}
                    catch(InvalidPathException ignored) {}
                }
            }
        }
        throw new IllegalArgumentException("缺少运行环境："+name+"。系统环境未找到该工具，请安装并加入 PATH，或在 NicoTools 设置中指定路径。");
    }
    private static boolean isWslBash(Path path) {
        String normalized=path.toAbsolutePath().normalize().toString().replace('\\','/').toLowerCase(Locale.ROOT);
        return normalized.endsWith("/windows/system32/bash.exe") || normalized.endsWith("/windows/sysnative/bash.exe");
    }
    public Map<String,String> executionEnvironment(Collection<String> requirements) {
        Map<String,String> env=new LinkedHashMap<>(environment);List<String> dirs=new ArrayList<>();
        // Validate only declared dependencies, while making explicitly configured tools usable by scripts.
        for(String required:requirements) {
            Path file=resolve(required,"");dirs.add(file.getParent().toString());env.put("POPTOOLS_"+required.toUpperCase(Locale.ROOT),file.toString());
        }
        for(var e:paths.entrySet()) {
            if(e.getValue().isBlank()) continue;
            Path file=Path.of(e.getValue());
            // An unrelated stale setting must not block ordinary scripts.
            if(Files.isRegularFile(file)) {dirs.add(file.getParent().toString());env.put("POPTOOLS_"+e.getKey().toUpperCase(Locale.ROOT),file.toString());}
        }
        String key=env.keySet().stream().filter(k->k.equalsIgnoreCase("PATH")).findFirst().orElse("PATH");
        env.put(key,String.join(java.io.File.pathSeparator,new LinkedHashSet<>(dirs))+(dirs.isEmpty()?"":java.io.File.pathSeparator)+env.getOrDefault(key,""));
        return env;
    }
}

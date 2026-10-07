package com.poptools.scripts;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;

/** Copies user-authored script files referenced by a PopTool directory export. */
public final class ScriptDirectoryTransfer {
    private static final Pattern FIRST=Pattern.compile("^\\s*(?:&\\s+)?(?:\"([^\"]+)\"|'([^']+)'|(\\S+))(.*)$",Pattern.DOTALL);
    private ScriptDirectoryTransfer() {}
    /** Portable backup: keep defaults and copy direct absolute script-file references. */
    public static void writeDirectory(Path directory,List<ScriptDefinition> scripts) throws Exception {
        Path output=directory.toAbsolutePath().normalize();
        Files.createDirectories(output.resolve("tools"));
        int index=0;
        for(var original:scripts) {
            ScriptDefinition script=ScriptJson.copy(original);
            String command=script.executor.command;
            Matcher matcher=FIRST.matcher(command);
            if(!command.contains("\n") && Set.of("python","powershell","bash","batch").contains(script.executor.kind) && matcher.matches()) {
                String token=matcher.group(1)!=null?matcher.group(1):matcher.group(2)!=null?matcher.group(2):matcher.group(3);
                if(token.matches("(?i).+\\.(py|ps1|sh|bat|cmd)")) {
                    Path file=Path.of(token);
                    if(file.isAbsolute()) {
                        if(!Files.isRegularFile(file))throw new IllegalArgumentException("导出时找不到脚本文件："+file);
                        Path tree=file.toRealPath().getParent();
                        Path relative=Path.of("scripts",UUID.randomUUID().toString());
                        Path destination=output.resolve(relative);Files.createDirectories(destination);
                        try(var entries=Files.walk(tree)) {
                            for(Path entry:entries.filter(p->!p.toAbsolutePath().normalize().startsWith(output)).toList()) {
                                if(Files.isSymbolicLink(entry))continue;
                                Path target=destination.resolve(tree.relativize(entry));
                                if(Files.isDirectory(entry))Files.createDirectories(target);else Files.copy(entry,target,StandardCopyOption.REPLACE_EXISTING);
                            }
                        }
                        String portable=relative.resolve(file.getFileName()).toString().replace('\\','/');
                        if(script.executor.kind.equals("powershell"))script.executor.command="& '"+portable.replace("'","''")+"'"+matcher.group(4);
                        else if(script.executor.kind.equals("bash"))script.executor.command="'"+portable.replace("'","'\"'\"'")+"'"+matcher.group(4);
                        else script.executor.command="\""+portable+"\""+matcher.group(4);
                    }
                }
            }
            Files.writeString(output.resolve("tools").resolve((++index)+"-"+script.id.replaceAll("[^A-Za-z0-9._-]","_")+".json"),ScriptJson.GSON.toJson(script),StandardCharsets.UTF_8);
        }
    }
    public static ScriptDefinition prepare(ScriptDefinition original,Path source,Path assets) throws Exception {
        ScriptDefinition script=ScriptJson.copy(original);String command=script.executor.command;
        if(command.contains("\n") || !Set.of("python","powershell","bash","batch").contains(script.executor.kind))return script;
        Matcher matcher=FIRST.matcher(command);if(!matcher.matches())return script;
        String token=matcher.group(1)!=null?matcher.group(1):matcher.group(2)!=null?matcher.group(2):matcher.group(3);
        String normalized=token.replace('\\','/');
        if(!normalized.matches("(?i).+\\.(py|ps1|sh|bat|cmd)"))return script;
        Path relative=Path.of(token);if(relative.isAbsolute())return script;
        Path sourceRoot=source.toRealPath();Path file=sourceRoot.resolve(relative).normalize();
        if(!file.startsWith(sourceRoot))throw new IllegalArgumentException("脚本文件引用超出导入目录："+token);
        if(!Files.isRegularFile(file))throw new IllegalArgumentException("导入目录缺少脚本文件："+token);
        if(!file.toRealPath().startsWith(sourceRoot))throw new IllegalArgumentException("脚本文件链接指向导入目录外部："+token);
        Path tree=normalized.startsWith("scripts/")?sourceRoot.resolve("scripts"):file.getParent();
        Path destination=assets.resolve(UUID.randomUUID().toString());Files.createDirectories(destination);
        try(var paths=Files.walk(tree)) {
            for(Path entry:paths.toList()) {
                if(Files.isSymbolicLink(entry))continue;
                Path target=destination.resolve(tree.relativize(entry));
                if(Files.isDirectory(entry))Files.createDirectories(target);else Files.copy(entry,target,StandardCopyOption.REPLACE_EXISTING);
            }
        }
        Path installed=destination.resolve(tree.relativize(file));String installedPath=installed.toString().replace('\\','/');
        // Python/BAT launchers recognize a file command. PowerShell/Bash need native shell invocation syntax.
        if(script.executor.kind.equals("powershell"))script.executor.command="& '"+installedPath.replace("'","''")+"'"+matcher.group(4);
        else if(script.executor.kind.equals("bash"))script.executor.command="'"+installedPath.replace("'","'\"'\"'")+"'"+matcher.group(4);
        else script.executor.command="\""+installedPath+"\""+matcher.group(4);
        return script;
    }
}

package com.poptools.scripts;

import java.util.*;
import java.util.regex.*;
import static com.poptools.scripts.ScriptDefinition.*;

/** Literal substitution, including PopTool legacy syntax. Never shell-escape values here. */
public final class ParameterTemplates {
    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{([^{}]+)}");
    private static final Pattern DECLARATION = Pattern.compile("^[ \\t]*(?:Var|pVal)[ \\t]+([^\\s:=]+)[ \\t]*(?::|=)[ \\t]*\\$\\{([^{}\\r\\n]+)}[ \\t]*(?:\\r?\\n|$)", Pattern.MULTILINE);
    private record Parsed(String id, String defaultValue, String kind, List<Option> options) {}
    private record Definition(String label, Parsed parsed, boolean declared) {}
    private ParameterTemplates() {}

    private static void validateId(String id) {
        if (id.isEmpty() || !id.codePoints().allMatch(c -> c=='_' || Character.isLetterOrDigit(c)))
            throw new IllegalArgumentException("参数名称只能包含中文、字母、数字或下划线："+id);
    }
    private static List<Option> choices(String value) {
        String[] parts=value.split("\\|",-1);
        if(parts.length<2 || Arrays.stream(parts).anyMatch(p -> !p.contains("="))) return List.of();
        List<Option> options=new ArrayList<>(); Set<String> labels=new HashSet<>();
        for(String part:parts) {
            int i=part.indexOf('='); String label=part.substring(0,i).strip(), v=part.substring(i+1).strip();
            if(label.isEmpty() || v.isEmpty() || !labels.add(label)) throw new IllegalArgumentException("下拉选项为空或重复："+part);
            options.add(new Option(label,v));
        }
        return options;
    }
    private static Parsed parse(String content) {
        int colon=content.indexOf(':'), equals=content.indexOf('=');
        boolean modern=colon>=0 && (equals<0 || colon<equals);
        if(!modern) {
            List<Option> options=choices(content);
            if(!options.isEmpty()) { validateId(options.getFirst().label); return new Parsed(options.getFirst().label,options.getFirst().value,"choice",options); }
        }
        int split=modern?colon:equals;
        String name=(split<0?content:content.substring(0,split)).strip();
        String value=split<0?null:content.substring(split+1);
        String[] names=name.split("@",-1); validateId(names[0]);
        String kind="text";
        if(names.length>1) {
            if(names.length!=2) throw new IllegalArgumentException("参数类型无效："+name);
            kind=switch(names[1].strip()) { case "file"->"file"; case "dir"->"directory"; default->throw new IllegalArgumentException("不支持的参数类型："+name); };
        }
        List<Option> options=modern?choices(value):List.of();
        if(!options.isEmpty()) {
            if(!kind.equals("text")) throw new IllegalArgumentException("文件或目录参数不能使用下拉选项");
            return new Parsed(names[0],options.getFirst().value,"choice",options);
        }
        return new Parsed(names[0],value,kind,List.of());
    }
    public static List<Parameter> synchronize(List<String> templates,List<Parameter> existing) {
        LinkedHashMap<String,Definition> definitions=new LinkedHashMap<>();
        for(String text:templates) {
            Matcher m=DECLARATION.matcher(text);
            while(m.find()) {
                Parsed id=parse(m.group(1)), p=parse(m.group(2));
                Definition d=new Definition(p.id,new Parsed(id.id,p.defaultValue,p.kind,p.options),true);
                Definition old=definitions.putIfAbsent(id.id,d);
                if(old!=null && !old.equals(d)) throw new IllegalArgumentException("参数设置了不同声明："+id.id);
            }
        }
        for(String text:templates) {
            Matcher m=PLACEHOLDER.matcher(DECLARATION.matcher(text).replaceAll(""));
            while(m.find()) {
                Parsed p=parse(m.group(1)); Definition old=definitions.get(p.id);
                if(old==null) { definitions.put(p.id,new Definition(p.id,p,false)); continue; }
                Parsed previous=old.parsed;
                if(p.defaultValue!=null) {
                    if(previous.defaultValue==null) definitions.put(p.id,new Definition(old.label,p,old.declared));
                    else if(!Objects.equals(previous.defaultValue,p.defaultValue) || !previous.kind.equals(p.kind) || !previous.options.equals(p.options))
                        throw new IllegalArgumentException("参数的默认值、类型或选项冲突："+p.id);
                } else if(!(old.declared && p.kind.equals("text")) && (!previous.kind.equals(p.kind) || !previous.options.equals(p.options)))
                    throw new IllegalArgumentException("参数的类型或选项冲突："+p.id);
            }
        }
        List<Parameter> result=new ArrayList<>();
        definitions.forEach((id,d)->{
            Parameter source=existing.stream().filter(p->id.equals(p.id)).findFirst().orElse(null);
            Parameter p=source==null?new Parameter():ScriptJson.copyParameter(source);
            p.id=id; if(source==null || d.declared) p.label=d.label;
            p.defaultValue=d.parsed.defaultValue==null?"":d.parsed.defaultValue;
            p.options=new ArrayList<>(d.parsed.options);
            if(!d.parsed.kind.equals("text") || List.of("choice","file","directory").contains(p.kind)) p.kind=d.parsed.kind;
            result.add(p);
        });
        return result;
    }
    public static List<String> templates(ScriptDefinition script) {
        List<String> templates=new ArrayList<>(); templates.add(script.executor.command);
        templates.addAll(script.executor.args); templates.addAll(script.executor.env.values());
        // PopTool also renders cwd. Include it so imported cwd-only parameters can be supplied.
        if(script.executor.cwd!=null) templates.add(script.executor.cwd);
        return templates;
    }
    public static String render(String template,Map<String,String> values) {
        Matcher m=PLACEHOLDER.matcher(DECLARATION.matcher(template).replaceAll("")); StringBuilder out=new StringBuilder();
        while(m.find()) { Parsed p=parse(m.group(1)); m.appendReplacement(out,Matcher.quoteReplacement(values.getOrDefault(p.id,p.defaultValue==null?"":p.defaultValue))); }
        m.appendTail(out); return out.toString();
    }
    public static String stripDefaults(String template) {
        Matcher matcher=PLACEHOLDER.matcher(template);StringBuilder result=new StringBuilder();
        while(matcher.find()) {
            Parsed p=parse(matcher.group(1));String replacement=matcher.group();
            if(p.options.isEmpty() && p.defaultValue!=null) {
                String name=p.id+(p.kind.equals("file")?"@file":p.kind.equals("directory")?"@dir":"");
                replacement="${"+name+"}";
            }
            matcher.appendReplacement(result,Matcher.quoteReplacement(replacement));
        }
        matcher.appendTail(result);return result.toString();
    }
    public static List<String> renderArguments(List<String> templates,Map<String,String> values,List<Parameter> parameters) {
        List<String> result=new ArrayList<>();
        for(String template:templates) {
            if(template.startsWith("?") && template.contains(":")) {
                int separator=template.indexOf(':');String id=template.substring(1,separator),value=values.getOrDefault(id,"");
                String kind=parameters.stream().filter(p->id.equals(p.id)).map(p->p.kind).findFirst().orElse("text");
                boolean truthy=!value.isEmpty();
                if(kind.equals("boolean"))truthy=value.equalsIgnoreCase("true") || value.equals("1");
                else if((kind.equals("integer") || kind.equals("number")) && !value.isEmpty())truthy=new java.math.BigDecimal(value).signum()!=0;
                if(!truthy)continue;template=template.substring(separator+1);
            }
            result.add(render(template,values));
        }
        return result;
    }
}

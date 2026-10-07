package com.poptools.scripts;

import java.util.*;

/** Matches PopTool v1 tool JSON; plugin-specific fields are additive. */
public final class ScriptDefinition {
    public int schema_version = 1;
    public String id = "custom." + UUID.randomUUID().toString().replace("-", "");
    public int revision = 1;
    public String origin = "custom", section = "custom", title = "新建脚本", description = "";
    public boolean editable = true, enabled = true;
    public List<String> tags = new ArrayList<>();
    public Executor executor = new Executor();
    public List<Parameter> parameters = new ArrayList<>();
    public Presentation presentation = new Presentation();
    public String interpreter = "";

    public static final class Executor {
        public String kind = "powershell", command = "", cwd, encoding = "utf-8";
        public List<String> args = new ArrayList<>(), requirements = new ArrayList<>();
        public Map<String,String> env = new LinkedHashMap<>();
        public Integer timeout_seconds;
        public String android_device_mode = "auto";
    }
    public static final class Parameter {
        public String id, label, kind = "text", placeholder = "";
        public Object defaultValue = "";
        public boolean required = true;
        public List<Option> options = new ArrayList<>();
    }
    public static final class Option {
        public String label, value;
        public Option() {}
        public Option(String label, String value) { this.label=label; this.value=value; }
        @Override public String toString() { return label; }
        @Override public boolean equals(Object other) { return other instanceof Option o && Objects.equals(label,o.label) && Objects.equals(value,o.value); }
        @Override public int hashCode() { return Objects.hash(label,value); }
    }
    public static final class Presentation {
        public String icon = "terminal", output_mode = "console";
        public int order = 100;
        public boolean confirm_before_run;
    }
    @Override public String toString() { return title; }
}

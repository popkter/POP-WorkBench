package com.poptools.scripts;

import com.android.tools.idea.run.deployment.selector.DevicesSelectedService;
import com.android.ddmlib.IDevice;
import com.intellij.openapi.project.Project;
import java.util.regex.Pattern;

public final class AndroidDevices {
    private static final Pattern ADB=Pattern.compile("(?i)(?:^|[\\s;|&\\\"'/\\\\])adb(?:\\.exe)?(?:[\\s\\\"']|$)");
    private AndroidDevices() {}
    public static boolean needed(ScriptDefinition s) {
        if(s.executor.requirements.contains("android_device"))return true;
        if(s.parameters.stream().anyMatch(p->p.kind.equals("android_device"))) return true;
        if(s.executor.android_device_mode.equals("use")) return true;
        if(s.executor.android_device_mode.equals("none")) return false;
        // Conservative convenience for direct adb snippets; Python/wrappers should declare mode=use.
        String command=s.executor.command;
        return ADB.matcher(command).find() && !command.strip().matches("(?is)adb(?:\\.exe)?\\s+(?:devices(?:\\s+-l)?|version|help)\\s*");
    }
    public static String selectedSerial(Project project) {
        var targets=DevicesSelectedService.getInstance(project).getSelectedTargets();
        return serialFromSelectedDevices(targets.stream().map(t->t.getDevice().getDdmlibDevice()).toList());
    }
    static String serialFromSelectedDevices(java.util.List<IDevice> selected) {
        if(selected.isEmpty()) throw new IllegalArgumentException("请在 Android Studio 运行工具栏选择 Android 设备");
        if(selected.size()!=1) throw new IllegalArgumentException("当前选择了多个设备，请在运行工具栏选择单个目标设备");
        IDevice device=selected.getFirst();
        if(device==null) throw new IllegalArgumentException("所选设备尚未连接或设备状态尚未就绪");
        if(!device.isOnline()) throw new IllegalArgumentException("所选设备不可用："+device.getState()+"（请检查连接和 USB 调试授权）");
        return device.getSerialNumber();
    }
}

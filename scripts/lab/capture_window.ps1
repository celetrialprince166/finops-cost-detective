# Capture a specific top-level window (matched by title substring) to a PNG.
# Bridges the Claude extension's in-memory screenshots to disk for the
# Cost Detective audit. Enumerates ALL top-level windows (not just each
# process's MainWindow) so it can find a specific Chrome tab/window.

param(
    [Parameter(Mandatory = $true)]
    [string]$OutPath,

    [string]$TitleMatch = "EC2"
)

Add-Type -AssemblyName System.Drawing

Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class Win {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder s, int n);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int n);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    public static List<IntPtr> Find(string match) {
        var hits = new List<IntPtr>();
        EnumWindows((h, l) => {
            if (!IsWindowVisible(h)) return true;
            int len = GetWindowTextLength(h);
            if (len == 0) return true;
            var sb = new StringBuilder(len + 1);
            GetWindowText(h, sb, sb.Capacity);
            string t = sb.ToString();
            if (t.IndexOf(match, StringComparison.OrdinalIgnoreCase) >= 0)
                hits.Add(h);
            return true;
        }, IntPtr.Zero);
        return hits;
    }

    public static string Title(IntPtr h) {
        int len = GetWindowTextLength(h);
        var sb = new StringBuilder(len + 1);
        GetWindowText(h, sb, sb.Capacity);
        return sb.ToString();
    }
}
"@

$hits = [Win]::Find($TitleMatch)
if ($hits.Count -eq 0) {
    Write-Error "No visible window matching '$TitleMatch'."
    exit 1
}
$hWnd = $hits[0]
Write-Output ("Matched: " + [Win]::Title($hWnd))

[Win]::ShowWindow($hWnd, 9) | Out-Null   # SW_RESTORE
[Win]::SetForegroundWindow($hWnd) | Out-Null
Start-Sleep -Milliseconds 800

$r = New-Object Win+RECT
[Win]::GetWindowRect($hWnd, [ref]$r) | Out-Null
$w = $r.Right - $r.Left
$h = $r.Bottom - $r.Top
if ($w -le 0 -or $h -le 0) { Write-Error "Bad window size $w x $h"; exit 1 }

$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen([System.Drawing.Point]::new($r.Left, $r.Top), [System.Drawing.Point]::Empty, [System.Drawing.Size]::new($w, $h))

$dir = Split-Path $OutPath -Parent
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output ("Saved {0}x{1} -> {2}" -f $w, $h, $OutPath)

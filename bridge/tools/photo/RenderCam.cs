using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

// Experimental: drive GECK's Render Window camera with window messages posted from inside
// the bottle (no macOS input). Usage: RenderCam <step> [<step> ...]
//   info | max | size:W:H | redraw | wheel:N | orbit:DX:DY | orbitsi:DX:DY | pan:DX:DY | key:C | click:X:Y | sleep:MS
class RenderCam {
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetParent(IntPtr h);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] static extern IntPtr SendMessageTimeout(IntPtr h, uint m, IntPtr w, IntPtr l, uint f, uint t, out IntPtr r);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] static extern bool InvalidateRect(IntPtr h, IntPtr r, bool erase);
    [DllImport("user32.dll")] static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] static extern uint SendInput(uint n, INPUT[] i, int size);
    [DllImport("user32.dll")] static extern short GetKeyState(int k);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] static extern void mouse_event(uint f, int dx, int dy, uint d, UIntPtr e);
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int L, T, R, B; }
    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort vk, scan; public uint flags, time; public IntPtr extra; public uint pad1, pad2; }
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public KEYBDINPUT ki; }

    static IntPtr render = IntPtr.Zero; static string title = "";
    static IntPtr Pack(int x, int y) { return (IntPtr)(((y & 0xffff) << 16) | (x & 0xffff)); }
    static void Post(uint m, int w, int x, int y) { PostMessage(render, m, (IntPtr)w, Pack(x, y)); }
    static void Send(uint m, int w, int x, int y) { IntPtr r; SendMessageTimeout(render, m, (IntPtr)w, Pack(x, y), 2, 1000, out r); }
    static void Shift(bool down) {
        var i = new INPUT[1]; i[0].type = 1; i[0].ki.vk = 0x10; i[0].ki.flags = down ? 0u : 2u;
        SendInput(1, i, Marshal.SizeOf(typeof(INPUT)));
    }

    static int Main(string[] args) {
        var procs = Process.GetProcessesByName("GECK");
        if (procs.Length != 1) { Console.WriteLine("{\"ok\":false,\"error\":\"expected one GECK, found " + procs.Length + "\"}"); return 2; }
        uint pid = (uint)procs[0].Id;
        EnumWindows((h, l) => {
            uint p; GetWindowThreadProcessId(h, out p); if (p != pid || !IsWindowVisible(h)) return true;
            var c = new StringBuilder(256); GetClassName(h, c, 256); var t = new StringBuilder(512); GetWindowText(h, t, 512);
            if (c.ToString() == "MonitorClass" && (t.ToString().Contains(" camera") || t.ToString() == "Render Window")) { render = h; title = t.ToString(); }
            return true; }, IntPtr.Zero);
        if (render == IntPtr.Zero) { Console.WriteLine("{\"ok\":false,\"error\":\"render window not found\"}"); return 2; }
        RECT cr; GetClientRect(render, out cr); int cx = (cr.R - cr.L) / 2, cy = (cr.B - cr.T) / 2;
        var log = new List<string>();
        foreach (var raw in args) {
            var a = raw.Split(':'); string op = a[0];
            if (op == "info") { RECT wr; GetWindowRect(render, out wr); log.Add("info " + title + " client " + (cr.R - cr.L) + "x" + (cr.B - cr.T) + " window " + wr.L + "," + wr.T + "," + wr.R + "," + wr.B + " shiftState " + GetKeyState(0x10)); }
            else if (op == "max") { ShowWindow(render, 3); }
            else if (op == "size") { SetWindowPos(render, IntPtr.Zero, 0, 0, int.Parse(a[1]), int.Parse(a[2]), 0x0004 | 0x0002); }
            else if (op == "redraw") { InvalidateRect(render, IntPtr.Zero, false); Post(0x200, 0, cx, cy); }
            else if (op == "wheel") { int n = int.Parse(a[1]); POINT p = new POINT { X = cx, Y = cy }; ClientToScreen(render, ref p);
                for (int i = 0; i < Math.Abs(n); i++) { PostMessage(render, 0x20A, (IntPtr)(((n > 0 ? 120 : -120) & 0xffff) << 16), Pack(p.X, p.Y)); Thread.Sleep(60); } }
            else if (op == "orbit" || op == "orbitsi" || op == "pan") {
                int dx = int.Parse(a[1]), dy = int.Parse(a[2]); int mk = op == "pan" ? 0x10 : 0x04;
                if (op == "orbitsi") Shift(true);
                Post(0x200, mk, cx, cy); Thread.Sleep(40);
                if (op == "pan") { Post(0x207, 0x10, cx, cy); Thread.Sleep(40); }
                for (int i = 1; i <= 10; i++) { Post(0x200, mk, cx + dx * i / 10, cy + dy * i / 10); Thread.Sleep(40); }
                if (op == "pan") Post(0x208, 0, cx + dx, cy + dy);
                Thread.Sleep(100); if (op == "orbitsi") Shift(false);
            }
            else if (op == "orbitreal" || op == "panreal") {
                // Real Wine input: foreground, cursor to centre, Shift (or middle button) held, relative moves.
                int dx = int.Parse(a[1]), dy = int.Parse(a[2]);
                SetForegroundWindow(render); Thread.Sleep(200);
                POINT p = new POINT { X = cx, Y = cy }; ClientToScreen(render, ref p); SetCursorPos(p.X, p.Y); Thread.Sleep(100);
                if (op == "orbitreal") Shift(true); else mouse_event(0x0020, 0, 0, 0, UIntPtr.Zero);
                Thread.Sleep(100);
                for (int i = 0; i < 20; i++) { mouse_event(0x0001, dx / 20, dy / 20, 0, UIntPtr.Zero); Thread.Sleep(30); }
                Thread.Sleep(100);
                if (op == "orbitreal") Shift(false); else mouse_event(0x0040, 0, 0, 0, UIntPtr.Zero);
                log.Add(op + " shiftAfter " + GetKeyState(0x10));
            }
            else if (op == "key") { int vk = (int)char.ToUpper(a[1][0]); PostMessage(render, 0x100, (IntPtr)vk, (IntPtr)1); PostMessage(render, 0x102, (IntPtr)(int)a[1][0], (IntPtr)1); PostMessage(render, 0x101, (IntPtr)vk, unchecked((IntPtr)(int)0xC0000001)); }
            else if (op == "click") { int x = int.Parse(a[1]), y = int.Parse(a[2]); Post(0x200, 0, x, y); Post(0x201, 1, x, y); Thread.Sleep(50); Post(0x202, 0, x, y); }
            else if (op == "sleep") { Thread.Sleep(int.Parse(a[1])); }
            else { log.Add("unknown " + op); }
            Thread.Sleep(150);
        }
        GetClientRect(render, out cr);
        Console.WriteLine("{\"ok\":true,\"title\":\"" + title.Replace("\"", "'") + "\",\"client\":[" + (cr.R - cr.L) + "," + (cr.B - cr.T) + "],\"log\":\"" + String.Join(" | ", log.ToArray()).Replace("\"", "'") + "\"}");
        return 0;
    }
}

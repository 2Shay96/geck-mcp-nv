using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

// One-off, user-approved: close GECK WITHOUT saving. Posts WM_CLOSE to the main window and answers
// only a save-changes prompt with "No". Any other dialog aborts. Usage: GeckQuit discard
class GeckQuit {
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr p, EnumProc cb, IntPtr l);
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    static string Cls(IntPtr h){var b=new StringBuilder(256);GetClassName(h,b,256);return b.ToString();}
    static string Txt(IntPtr h){var b=new StringBuilder(1024);GetWindowText(h,b,1024);return b.ToString();}
    static string Out(bool ok, List<string> log){return "{\"ok\":"+(ok?"true":"false")+",\"log\":\""+String.Join(" | ",log.ToArray()).Replace("\\","/").Replace("\"","'")+"\"}";}
    static int Main(string[] args) {
        var log = new List<string>();
        if (args.Length != 1 || args[0] != "discard") { log.Add("usage: GeckQuit discard"); Console.WriteLine(Out(false,log)); return 2; }
        var procs = Process.GetProcessesByName("GECK");
        if (procs.Length != 1) { log.Add("expected one GECK, found "+procs.Length); Console.WriteLine(Out(false,log)); return 2; }
        var proc = procs[0]; uint pid = (uint)proc.Id; IntPtr main = IntPtr.Zero;
        EnumWindows((h,l)=>{uint p;GetWindowThreadProcessId(h,out p);if(p==pid&&IsWindowVisible(h)&&Txt(h).StartsWith("Garden of Eden Creation Kit"))main=h;return true;},IntPtr.Zero);
        if (main == IntPtr.Zero) { log.Add("main window not found"); Console.WriteLine(Out(false,log)); return 2; }
        log.Add("closing: " + Txt(main));
        PostMessage(main, 0x0010, IntPtr.Zero, IntPtr.Zero);
        var watch = Stopwatch.StartNew(); bool answered = false;
        while (watch.ElapsedMilliseconds < 30000) {
            Thread.Sleep(300);
            if (proc.HasExited) { log.Add("exited"); Console.WriteLine(Out(true,log)); return 0; }
            var dialogs = new List<IntPtr>();
            EnumWindows((h,l)=>{uint p;GetWindowThreadProcessId(h,out p);if(p==pid&&IsWindowVisible(h)&&Cls(h)=="#32770")dialogs.Add(h);return true;},IntPtr.Zero);
            foreach (var d in dialogs) {
                var texts = new List<string>(); IntPtr no = IntPtr.Zero;
                EnumChildWindows(d,(c,l)=>{string t=Txt(c);texts.Add(Cls(c)+":"+t);if(Cls(c)=="Button"&&(t=="&No"||t=="No"))no=c;return true;},IntPtr.Zero);
                string all = String.Join(" / ", texts.ToArray());
                if (!answered && no != IntPtr.Zero && all.ToLower().Contains("save")) { log.Add("prompt: " + Txt(d) + " :: " + all); PostMessage(no, 0x00F5, IntPtr.Zero, IntPtr.Zero); answered = true; }
                else if (!all.ToLower().Contains("save")) { log.Add("unexpected dialog, aborting: " + Txt(d) + " :: " + all); Console.WriteLine(Out(false,log)); return 3; }
            }
        }
        log.Add("GECK did not exit"); Console.WriteLine(Out(false,log)); return 4;
    }
}

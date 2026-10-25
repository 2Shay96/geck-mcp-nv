// Synthetic Win32 controls exercise the actual Probe implementation without GECK/game data.
using System;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;

class ReliabilityHost {
    delegate IntPtr WndProc(IntPtr h,uint m,IntPtr w,IntPtr l);
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct WNDCLASS {
        public uint style; public WndProc proc; public int clsExtra,wndExtra;
        public IntPtr instance,icon,cursor,background; public string menu,name;
    }
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern ushort RegisterClass(ref WNDCLASS c);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr DefWindowProc(IntPtr h,uint m,IntPtr w,IntPtr l);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr CreateWindowEx(uint ex,string cls,string title,uint style,int x,int y,int w,int h,IntPtr parent,IntPtr menu,IntPtr instance,IntPtr param);
    [DllImport("user32.dll",EntryPoint="CreateWindowExA",CharSet=CharSet.Ansi)] static extern IntPtr CreateAnsi(uint ex,string cls,string title,uint style,int x,int y,int w,int h,IntPtr parent,IntPtr menu,IntPtr instance,IntPtr param);
    [DllImport("user32.dll",CharSet=CharSet.Ansi)] static extern bool SetWindowTextA(IntPtr h,string text);
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
    [DllImport("user32.dll")] static extern bool DestroyWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h,int cmd);
    [DllImport("user32.dll")] static extern bool EnableWindow(IntPtr h,bool enabled);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibrary(string file);
    [DllImport("comctl32.dll")] static extern void InitCommonControls();
    static readonly WndProc callback=DefWindowProc;
    static readonly BindingFlags PrivateStatic=BindingFlags.NonPublic|BindingFlags.Static;
    static object Call(string name,params object[] args) {return typeof(Probe).GetMethod(name,PrivateStatic).Invoke(null,args);}
    static IntPtr Make(string cls,string title,IntPtr owner) {
        var c=new WNDCLASS{proc=callback,name=cls};RegisterClass(ref c);
        IntPtr h=CreateWindowEx(0,cls,title,0x00CF0000,0,0,300,200,owner,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero);
        if(h==IntPtr.Zero)throw new Exception("fixture window failed: "+cls);return h;
    }
    static void Assert(bool condition,string message){if(!condition)throw new Exception(message);}
    static void Insert(IntPtr list,int row,string label) {
        IntPtr text=Marshal.StringToHGlobalUni(label),item=Marshal.AllocHGlobal(60);
        try {for(int i=0;i<60;i++)Marshal.WriteByte(item,i,0);Marshal.WriteInt32(item,0,1);Marshal.WriteInt32(item,4,row);Marshal.WriteIntPtr(item,20,text);
            Assert(SendMessage(list,0x104D,IntPtr.Zero,item).ToInt32()>=0,"list insert failed");
        }finally{Marshal.FreeHGlobal(text);Marshal.FreeHGlobal(item);}
    }
    public static int Main() {
        try {
            LoadLibrary("riched20.dll");
            IntPtr root=Make("Garden of Eden Creation Kit","Garden of Eden Creation Kit - [Fixture.esp]",IntPtr.Zero);
            IntPtr pane=Make("FaceClass","Object Window",root);ShowWindow(pane,4);
            IntPtr cell=Make("ViewerClass","Cell View",root);ShowWindow(cell,4);
            IntPtr render=Make("MonitorClass","Render Window",root);ShowWindow(render,4);
            IntPtr edit=CreateAnsi(0,"RichEdit20A","",0x40000000|4,0,0,200,100,root,(IntPtr)1166,IntPtr.Zero,IntPtr.Zero);
            Assert(edit!=IntPtr.Zero,"RichEdit20A creation");
            SendMessage(edit,0x435,IntPtr.Zero,(IntPtr)(1024*1024));
            foreach(int length in new[]{2049,32021,63939,65535,66000,131000}) {
                string text="scn Fixture\r\n; caf\u00e9 \u20ac "+new string('x',length)+"\r\n";
                Assert(SetWindowTextA(edit,text),"SetWindowTextA failed");
                string observed=(string)Call("FullScriptText",edit);
                Assert(observed.Replace("\r\n","\n")==text.Replace("\r\n","\n"),"full source differs at "+length);
                Console.WriteLine("full-source "+length+" verified");
            }
            typeof(Probe).GetField("target",PrivateStatic).SetValue(null,(uint)Process.GetCurrentProcess().Id);
            Call("Discover");string before=(string)Call("EditorWindows");
            Assert(before.Contains("\"mainWindow\":{")&&before.Contains("\"visible\":false"),"hidden root missing from visibility");
            object[] showArgs={null};string restored=(string)Call("WindowsShow",showArgs);
            Assert(IsWindowVisible(root)&&restored.Contains("\"allVisible\":true"),"root restore unverified");
            Console.WriteLine("hidden-root restore verified");
            InitCommonControls();
            IntPtr list=CreateWindowEx(0,"SysListView32","",0x40000001,0,0,200,100,root,(IntPtr)1018,IntPtr.Zero,IntPtr.Zero);
            for(int i=0;i<10000;i++)Insert(list,i,"SyntheticRow"+i);
            Call("Discover");object window=null;
            foreach(object candidate in (System.Collections.IEnumerable)typeof(Probe).GetField("windows",PrivateStatic).GetValue(null))
                if((IntPtr)candidate.GetType().GetField("Handle").GetValue(candidate)==list)window=candidate;
            Assert(window!=null,"list inventory missing");
            Assert((int)Call("FindObjectRow",window,"SyntheticRow9999")==9999,"native list identity readback failed");
            Insert(list,10000,"SyntheticRow9999");bool ambiguous=false;
            try{Call("FindObjectRow",window,"SyntheticRow9999");}catch(TargetInvocationException){ambiguous=true;}
            Assert(ambiguous,"duplicate native list identity accepted");DestroyWindow(list);
            Console.WriteLine("native 10000-row unique/ambiguous search verified");
            Environment.SetEnvironmentVariable("GECK_BRIDGE_PLUGIN","Fixture.esp");
            IntPtr editor=Make("SyntheticScriptEditor","Script Edit [Fixture]",root);ShowWindow(editor,4);
            IntPtr script=CreateAnsi(0,"RichEdit20A","",0x40000000|4,0,0,200,100,editor,(IntPtr)1166,IntPtr.Zero,IntPtr.Zero);
            SetWindowTextA(script,"scn Fixture\r\n");
            IntPtr modal=CreateWindowEx(0,"#32770","Save Current Script?",0x00CF0000,0,0,300,200,editor,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero);
            CreateWindowEx(0,"Static","Save Fixture?",0x50000000,0,0,180,20,modal,(IntPtr)1001,IntPtr.Zero,IntPtr.Zero);
            CreateWindowEx(0,"Button","&Yes",0x50000000,0,30,80,30,modal,(IntPtr)6,IntPtr.Zero,IntPtr.Zero);
            ShowWindow(modal,4);EnableWindow(editor,false);Call("Discover");
            string full=(string)Call("FullScriptText",script);string hash=(string)Call("SourceHash",full);
            object[] resolveArgs={"Fixture",hash,null};
            Assert(((string)Call("ScriptResolveSave",resolveArgs)).Contains("\"resolved\":true"),"owned save prompt rejected");
            bool rejected=false;try{Call("ScriptResolveSave",new object[]{"Fixture",new string('0',64),null});}catch(TargetInvocationException){rejected=true;}
            Assert(rejected,"wrong-source prompt was accepted");
            DestroyWindow(modal);EnableWindow(editor,true);
            bool guarded=false;try{Call("ScriptEditorClose",new object[]{"Fixture",new string('0',64),null});}catch(TargetInvocationException){guarded=true;}
            Assert(guarded,"checkpoint close accepted changed source");
            ShowWindow(editor,0);Call("Discover");
            Assert(Call("ScriptEditor")==null,"hidden retained editor treated as open");
            Assert(((string)Call("ScriptEditorInspect")).Contains("\"editor\":null"),"hidden editor inspect remains open");
            Assert(((string)Call("ScriptEditorClose",new object[]{null,null,null})).Contains("\"closed\":true"),"hidden retained editor close failed");
            Console.WriteLine("hidden retained script editor verified closed");
            DestroyWindow(editor);
            Console.WriteLine("owned prompt/source guard verified");
            DestroyWindow(edit);bool unreadable=false;
            try{Call("FullScriptText",edit);}catch(TargetInvocationException){unreadable=true;}
            Assert(unreadable,"unreadable source became empty success");
            Console.WriteLine("unreadable source remains unknown");
            DestroyWindow(root);DestroyWindow(pane);DestroyWindow(cell);DestroyWindow(render);
            Console.WriteLine("PASS synthetic native helper checks");return 0;
        } catch(Exception error) {Console.Error.WriteLine(error);return 1;}
    }
}

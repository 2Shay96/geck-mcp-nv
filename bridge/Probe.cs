using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

// Bounded GECK control bridge. Placement uses one exact, verified drag gesture.
class Probe {
    static Dictionary<string,string> requestEnv;
    static string Config(string name,string fallback) {string v;if(requestEnv!=null){if(!requestEnv.TryGetValue("GECK_BRIDGE_"+name,out v))v=null;}else v=Environment.GetEnvironmentVariable("GECK_BRIDGE_"+name);return String.IsNullOrEmpty(v)?fallback:v;}
    static string ExpectedPlugin() {string p=Config("PLUGIN","SalvatorePrototype.esp");if(System.IO.Path.GetFileName(p)!=p||!p.EndsWith(".esp",StringComparison.OrdinalIgnoreCase))throw new Exception("invalid configured plugin");return p;}
    static string ExpectedTitle() {return "Garden of Eden Creation Kit - ["+ExpectedPlugin()+"]";}
    static string Session() {var p=Process.GetProcessById((int)target);return target+":"+p.StartTime.ToUniversalTime().Ticks;}
    static void GuardSession() {string expected=Config("SESSION","");if(expected!=""&&expected!=Session())throw new Exception("STALE_SESSION: editor restarted");}
    static void GuardRecord(string editorId) {string allowed=Config("RECORDS","SalvatoreStatic");if(Array.IndexOf(allowed.Split('|'),editorId)<0)throw new Exception("record is not configured for editing");}

    delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr p);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr h, EnumProc f, IntPtr p);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern int GetDlgCtrlID(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr SendMessageTimeout(IntPtr h, uint m, IntPtr w, IntPtr l, uint flags, uint ms, out IntPtr result);
    [DllImport("user32.dll", CharSet=CharSet.Unicode, EntryPoint="SendMessageTimeoutW")] static extern IntPtr TextMessage(IntPtr h, uint m, IntPtr w, StringBuilder l, uint flags, uint ms, out IntPtr result);
    [DllImport("user32.dll", CharSet=CharSet.Unicode, EntryPoint="SendMessageTimeoutW")] static extern IntPtr SetTextMessage(IntPtr h, uint m, IntPtr w, string l, uint flags, uint ms, out IntPtr result);
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll")] static extern IntPtr VirtualAllocEx(IntPtr p, IntPtr a, UIntPtr n, uint type, uint protect);
    [DllImport("kernel32.dll")] static extern bool VirtualFreeEx(IntPtr p, IntPtr a, UIntPtr n, uint type);
    [DllImport("kernel32.dll")] static extern bool WriteProcessMemory(IntPtr p, IntPtr a, byte[] b, UIntPtr n, out UIntPtr written);
    [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr p, IntPtr a, byte[] b, UIntPtr n, out UIntPtr read);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr p);

    [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr h, uint flags);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h, uint flags);
    [DllImport("user32.dll")] static extern bool IsWindowEnabled(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetMenu(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetSubMenu(IntPtr h,int index);
    [DllImport("user32.dll")] static extern int GetMenuItemCount(IntPtr h);
    [DllImport("user32.dll")] static extern uint GetMenuItemID(IntPtr h,int index);
    [DllImport("user32.dll")] static extern uint GetMenuState(IntPtr h,uint item,uint flags);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetMenuString(IntPtr h,uint item,StringBuilder text,int max,uint flags);
    [DllImport("user32.dll",SetLastError=true)] static extern bool PostMessage(IntPtr h,uint msg,IntPtr w,IntPtr l);
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left,Top,Right,Bottom; }
    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X,Y; }
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h,out RECT rect);
    [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr h,out RECT rect);
    [DllImport("user32.dll")] static extern bool ClientToScreen(IntPtr h,ref POINT point);
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x,int y);
    [DllImport("user32.dll")] static extern void mouse_event(uint flags,uint dx,uint dy,uint data,UIntPtr extra);
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h,int cmd);
    [DllImport("user32.dll")] static extern bool InvalidateRect(IntPtr h,IntPtr rect,bool erase);
    [DllImport("user32.dll")] static extern uint SendInput(uint count,KEYINPUT[] inputs,int size);
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    [StructLayout(LayoutKind.Sequential)] struct KEYINPUT { public uint Type; public ushort Vk,Scan; public uint Flags,Time; public IntPtr Extra; public uint Pad1,Pad2; }
    [DllImport("user32.dll",SetLastError=true)] static extern bool SetWindowPos(IntPtr h,IntPtr after,int x,int y,int cx,int cy,uint flags);
    static void MenuWalk(IntPtr menu,IntPtr owner,string path,List<string> rows,int depth) {
        if(depth>12||rows.Count>1000)throw new Exception("menu inventory limit exceeded");
        int count=GetMenuItemCount(menu);if(count<0)throw new Exception("GetMenuItemCount failed");
        for(int i=0;i<count;i++) {
            var label=new StringBuilder(1024);GetMenuString(menu,(uint)i,label,label.Capacity,0x400);
            string here=path.Length==0?label.ToString():path+" / "+label;
            uint state=GetMenuState(menu,(uint)i,0x400);if(state==0xffffffff)throw new Exception("GetMenuState failed");
            IntPtr sub=GetSubMenu(menu,i);uint id=GetMenuItemID(menu,i);
            rows.Add("{\"owner\":"+owner.ToInt64()+",\"path\":"+J(here)+",\"id\":"+id+",\"enabled\":"+((state&3)==0).ToString().ToLower()+",\"submenu\":"+(sub!=IntPtr.Zero).ToString().ToLower()+"}");
            if(sub!=IntPtr.Zero)MenuWalk(sub,owner,here,rows,depth+1);
        }
    }
    static string Menus() {var rows=new List<string>();bool complete=true;foreach(var w in windows){if(w.Parent!=IntPtr.Zero)continue;IntPtr m=GetMenu(w.Handle);if(m!=IntPtr.Zero){try{MenuWalk(m,w.Handle,"",rows,0);}catch(Exception ex){complete=false;rows.Add("{\"owner\":"+w.Handle.ToInt64()+",\"class\":"+J(w.ClassName)+",\"menuHandle\":"+m.ToInt64()+",\"error\":"+J(ex.Message)+"}");}}}return "{\"liveStateVerified\":"+complete.ToString().ToLower()+",\"items\":["+String.Join(",",rows.ToArray())+"]}";}
    delegate bool ResourceProc(IntPtr module,IntPtr type,IntPtr name,IntPtr param);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr LoadLibraryEx(string path,IntPtr file,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool EnumResourceNames(IntPtr module,IntPtr type,ResourceProc callback,IntPtr param);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadMenu(IntPtr module,IntPtr name);
    [DllImport("user32.dll")] static extern bool DestroyMenu(IntPtr menu);
    static string ResourceMenus() {
        string path=GeckExecutable();
        IntPtr module=LoadLibraryEx(path,IntPtr.Zero,2);if(module==IntPtr.Zero)throw new Exception("resource load failed: "+Marshal.GetLastWin32Error());
        var rows=new List<string>();string failure=null;
        try {bool ok=EnumResourceNames(module,(IntPtr)4,delegate(IntPtr m,IntPtr t,IntPtr name,IntPtr unused){
            IntPtr menu=LoadMenu(m,name);if(menu==IntPtr.Zero){failure="LoadMenu failed";return false;}
            try {string label=((uint)name.ToInt32()<=65535)?name.ToInt32().ToString():Marshal.PtrToStringUni(name);MenuWalk(menu,IntPtr.Zero,"resource:"+label,rows,0);return true;}
            catch(Exception ex){failure=ex.Message;return false;}finally{DestroyMenu(menu);}
        },IntPtr.Zero);if(!ok||failure!=null)throw new Exception(failure??"resource enumeration failed");
        return "{\"source\":"+J(path)+",\"liveStateVerified\":false,\"items\":["+String.Join(",",rows.ToArray())+"]}";
        }finally{FreeLibrary(module);}
    }
    class WindowInfo { public IntPtr Handle, Parent, ActualParent, Owner; public string ClassName, Text; public int Id; public bool Visible, Enabled; }
    const uint TimeoutMs=500;
    static uint target;
    static readonly List<WindowInfo> windows=new List<WindowInfo>();
    static string J(string s) { if(s==null)return "null";var b=new StringBuilder("\"");foreach(char c in s){if(c=='\\')b.Append("\\\\");else if(c=='\"')b.Append("\\\"");else if(c=='\r')b.Append("\\r");else if(c=='\n')b.Append("\\n");else if(c=='\t')b.Append("\\t");else if(c<32||c>126)b.Append("\\u"+((int)c).ToString("x4"));else b.Append(c);}b.Append('\"');return b.ToString(); }
    static long Msg(IntPtr h,uint m,IntPtr w,IntPtr l) { IntPtr r; if(SendMessageTimeout(h,m,w,l,2,TimeoutMs,out r)==IntPtr.Zero)throw new Exception("message timed out or failed"); return r.ToInt64(); }
    static string Text(IntPtr h) { var b=new StringBuilder(2048); IntPtr r; if(TextMessage(h,13,(IntPtr)b.Capacity,b,2,TimeoutMs,out r)==IntPtr.Zero)throw new Exception("WM_GETTEXT timed out or failed"); return b.ToString(); }
    static string Class(IntPtr h) { var b=new StringBuilder(256); GetClassName(h,b,b.Capacity); return b.ToString(); }
    static bool AddWindow(IntPtr h,IntPtr parent) { uint pid; GetWindowThreadProcessId(h,out pid); if(pid!=target)return true; string text; try{text=Text(h);}catch{text="<unavailable>";} windows.Add(new WindowInfo{Handle=h,Parent=parent,ActualParent=GetAncestor(h,1),Owner=GetWindow(h,4),Enabled=IsWindowEnabled(h),ClassName=Class(h),Text=text,Id=GetDlgCtrlID(h),Visible=IsWindowVisible(h)}); return true; }
    static void Discover() { windows.Clear(); EnumWindows(delegate(IntPtr top,IntPtr unused){ uint pid; GetWindowThreadProcessId(top,out pid); if(pid!=target)return true; AddWindow(top,IntPtr.Zero); EnumChildWindows(top,delegate(IntPtr child,IntPtr p){return AddWindow(child,top);},IntPtr.Zero); return true;},IntPtr.Zero); }
    static WindowInfo Unique(string name,string cls,int id,string parentClass) { var matches=new List<WindowInfo>(); foreach(var w in windows){ if(w.ClassName!=cls||w.Id!=id)continue; var parent=windows.Find(x=>x.Handle==w.Parent); if(parent!=null&&parent.ClassName==parentClass)matches.Add(w); } if(matches.Count!=1)throw new Exception(name+" selector matched "+matches.Count+" controls"); return matches[0]; }
    static WindowInfo MainWindow() { var matches=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.ClassName=="Garden of Eden Creation Kit"); if(matches.Count!=1)throw new Exception("main window selector matched "+matches.Count+" windows"); return matches[0]; }
    static int Count(WindowInfo w) { return checked((int)Msg(w.Handle,0x1004,IntPtr.Zero,IntPtr.Zero)); }
    static string TreeText(WindowInfo tree,IntPtr item) {
        if(item==IntPtr.Zero)return null;
        IntPtr process=OpenProcess(0x38,false,target); if(process==IntPtr.Zero)throw new Exception("OpenProcess failed for category tree");
        IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,(UIntPtr)2304,0x3000,4); bool safeToFree=true;
        try {
            if(memory==IntPtr.Zero)throw new Exception("category buffer allocation failed");
            byte[] tvitem=new byte[40];
            Array.Copy(BitConverter.GetBytes(1),0,tvitem,0,4);
            Array.Copy(BitConverter.GetBytes(item.ToInt32()),0,tvitem,4,4);
            Array.Copy(BitConverter.GetBytes(memory.ToInt32()+256),0,tvitem,16,4);
            Array.Copy(BitConverter.GetBytes(1024),0,tvitem,20,4);
            UIntPtr transferred;
            if(!WriteProcessMemory(process,memory,tvitem,(UIntPtr)tvitem.Length,out transferred)||transferred.ToUInt64()!=(ulong)tvitem.Length)throw new Exception("category buffer write failed");
            try { Msg(tree.Handle,0x113E,IntPtr.Zero,memory); } catch { safeToFree=false; throw; }
            byte[] text=new byte[2048];
            if(!ReadProcessMemory(process,(IntPtr)(memory.ToInt32()+256),text,(UIntPtr)text.Length,out transferred))throw new Exception("category buffer read failed");
            return Encoding.Unicode.GetString(text).Split('\0')[0];
        } finally { if(memory!=IntPtr.Zero&&safeToFree)VirtualFreeEx(process,memory,UIntPtr.Zero,0x8000); CloseHandle(process); }
    }
    static string SelectedTreeText(WindowInfo tree) { return TreeText(tree,(IntPtr)Msg(tree.Handle,0x110A,(IntPtr)9,IntPtr.Zero)); }
    static IntPtr TreeRelated(WindowInfo tree,int relation,IntPtr item) { return (IntPtr)Msg(tree.Handle,0x110A,(IntPtr)relation,item); }
    static bool FindTreePath(WindowInfo tree,IntPtr item,string[] parts,int depth,out IntPtr found) {
        found=IntPtr.Zero;
        while(item!=IntPtr.Zero) {
            if(TreeText(tree,item)==parts[depth]) {
                if(depth==parts.Length-1){found=item;return true;}
                IntPtr child=TreeRelated(tree,4,item);
                if(child!=IntPtr.Zero&&FindTreePath(tree,child,parts,depth+1,out found))return true;
            }
            item=TreeRelated(tree,1,item);
        }
        return false;
    }
    static string TreePath(WindowInfo tree,IntPtr item) {
        var parts=new List<string>();
        while(item!=IntPtr.Zero){parts.Insert(0,TreeText(tree,item));item=TreeRelated(tree,3,item);}
        return String.Join(" / ",parts.ToArray());
    }
    static string[] PathParts(string path) {
        string normalized=path.Replace(" > ","/").Replace(">","/").Replace("\\","/");
        string[] raw=normalized.Split(new[]{'/'},StringSplitOptions.RemoveEmptyEntries);
        for(int i=0;i<raw.Length;i++)raw[i]=raw[i].Trim();
        if(raw.Length==0)throw new Exception("category path is empty");
        return raw;
    }
    static string ListCell(WindowInfo list,int row) {return ListColumn(list,row,0);}
    static string ListColumn(WindowInfo list,int row,int column) {
        IntPtr process=OpenProcess(0x38,false,target); if(process==IntPtr.Zero)throw new Exception("OpenProcess failed for object list");
        IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,(UIntPtr)2304,0x3000,4); bool safe=true;
        try { if(memory==IntPtr.Zero)throw new Exception("list buffer allocation failed"); byte[] item=new byte[60]; Array.Copy(BitConverter.GetBytes(column),0,item,8,4); Array.Copy(BitConverter.GetBytes(row),0,item,4,4); Array.Copy(BitConverter.GetBytes(memory.ToInt32()+256),0,item,20,4); Array.Copy(BitConverter.GetBytes(1024),0,item,24,4); UIntPtr n; if(!WriteProcessMemory(process,memory,item,(UIntPtr)item.Length,out n))throw new Exception("list buffer write failed"); try{Msg(list.Handle,0x1073,(IntPtr)row,memory);}catch{safe=false;throw;} byte[] text=new byte[2048]; if(!ReadProcessMemory(process,(IntPtr)(memory.ToInt32()+256),text,(UIntPtr)text.Length,out n))throw new Exception("list buffer read failed"); return Encoding.Unicode.GetString(text).Split('\0')[0]; }
        finally { if(memory!=IntPtr.Zero&&safe)VirtualFreeEx(process,memory,UIntPtr.Zero,0x8000); CloseHandle(process); }
    }
    static RECT ListItemRect(WindowInfo list,int row) {
        IntPtr process=OpenProcess(0x38,false,target);if(process==IntPtr.Zero)throw new Exception("OpenProcess failed for item bounds");IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,(UIntPtr)16,0x3000,4);bool safe=true;
        try{if(memory==IntPtr.Zero)throw new Exception("item-bounds allocation failed");byte[] data=new byte[16];Array.Copy(BitConverter.GetBytes(0),0,data,0,4);UIntPtr n;if(!WriteProcessMemory(process,memory,data,(UIntPtr)data.Length,out n))throw new Exception("item-bounds write failed");try{if(Msg(list.Handle,0x100E,(IntPtr)row,memory)==0)throw new Exception("LVM_GETITEMRECT failed");}catch{safe=false;throw;}if(!ReadProcessMemory(process,memory,data,(UIntPtr)data.Length,out n))throw new Exception("item-bounds read failed");return new RECT{Left=BitConverter.ToInt32(data,0),Top=BitConverter.ToInt32(data,4),Right=BitConverter.ToInt32(data,8),Bottom=BitConverter.ToInt32(data,12)};}
        finally{if(memory!=IntPtr.Zero&&safe)VirtualFreeEx(process,memory,UIntPtr.Zero,0x8000);CloseHandle(process);}
    }
    static string WindowJson(WindowInfo w) { return "{\"handle\":"+w.Handle.ToInt64()+",\"parentHandle\":"+w.Parent.ToInt64()+",\"id\":"+w.Id+",\"class\":"+J(w.ClassName)+",\"visible\":"+w.Visible.ToString().ToLower()+",\"text\":"+J(w.Text)+",\"actualParent\":"+w.ActualParent.ToInt64()+",\"owner\":"+w.Owner.ToInt64()+",\"enabled\":"+w.Enabled.ToString().ToLower()+"}"; }
    static string Result(bool ok,string operation,string before,string after,long elapsed,string error) { return "{\"ok\":"+ok.ToString().ToLower()+",\"operation\":"+J(operation)+",\"target\":\"GECK\",\"before\":"+(before??"null")+",\"after\":"+(after??"null")+",\"elapsedMs\":"+elapsed+",\"error\":"+J(error)+",\"worker\":"+WorkerJson(elapsed)+"}"; }
    static string Status() {
        var clock=Stopwatch.StartNew();var marks=new StringBuilder();
        Action<string> mark=delegate(string name){marks.Append(marks.Length==0?"":",").Append("\""+name+"\":"+clock.ElapsedMilliseconds);clock.Restart();};
        var main=MainWindow(); var list=Unique("object list","SysListView32",1041,"FaceClass"); var filter=Unique("object filter","Edit",2557,"FaceClass"); Unique("category tree","SysTreeView32",2093,"FaceClass");mark("selectors");
        string session=Session();mark("session");string exe=GeckExecutable();mark("executable");string top=TopWindows();mark("topWindows");
        string filterText=Text(filter.Handle);mark("filterText");int count=Count(list);mark("listCount");
        return "{\"pid\":"+target+",\"pointerBytes\":"+IntPtr.Size+",\"windowCount\":"+windows.Count+",\"editorTitle\":"+J(main.Text)+",\"sessionId\":"+J(session)+",\"executable\":"+J(exe)+",\"unsavedChanges\":"+main.Text.EndsWith("*").ToString().ToLower()+",\"windows\":"+top+",\"objectWindow\":{\"filter\":"+J(filterText)+",\"listCount\":"+count+",\"selectors\":{\"filterId\":2557,\"listId\":1041,\"categoryTreeId\":2093}},\"timingMs\":{"+marks+"}}";
    }
    static string Inspect(int limit) { var b=new StringBuilder("{\"count\":"+windows.Count+",\"returned\":"+Math.Min(limit,windows.Count)+",\"controls\":["); for(int i=0;i<Math.Min(limit,windows.Count);i++){if(i>0)b.Append(',');b.Append(WindowJson(windows[i]));} b.Append("]}");return b.ToString(); }
    static void SetText(WindowInfo w,string value) { IntPtr r; if(SetTextMessage(w.Handle,12,IntPtr.Zero,value,2,TimeoutMs,out r)==IntPtr.Zero)throw new Exception("WM_SETTEXT timed out or failed"); }
    static string FilterState(WindowInfo filter,WindowInfo list,WindowInfo tree) { int count=Count(list); var b=new StringBuilder("{\"text\":"+J(Text(filter.Handle))+",\"category\":"+J(SelectedTreeText(tree))+",\"listCount\":"+count+",\"rows\":["); for(int i=0;i<Math.Min(count,10);i++){if(i>0)b.Append(',');b.Append(J(ListCell(list,i)));} b.Append("]}");return b.ToString(); }
    static string FilterSet(string value,out string before) { var filter=Unique("object filter","Edit",2557,"FaceClass"); var list=Unique("object list","SysListView32",1041,"FaceClass"); var tree=Unique("category tree","SysTreeView32",2093,"FaceClass"); before=FilterState(filter,list,tree); SetText(filter,value); if(Text(filter.Handle)!=value)throw new Exception("filter readback did not match requested text"); int previous=-1,stable=0,current=-1; var wait=Stopwatch.StartNew(); while(wait.ElapsedMilliseconds<3000){ current=Count(list); if(current==previous)stable++;else stable=0; if(stable>=5&&wait.ElapsedMilliseconds>=750)break; previous=current; System.Threading.Thread.Sleep(100); } if(stable<5)throw new Exception("object list did not stabilize within 3000 ms"); return FilterState(filter,list,tree); }
    static void WaitListStable(WindowInfo list) { int previous=-1,stable=0; var wait=Stopwatch.StartNew(); while(wait.ElapsedMilliseconds<3000){int current=Count(list);stable=current==previous?stable+1:0;previous=current;if(stable>=5&&wait.ElapsedMilliseconds>=750)return;System.Threading.Thread.Sleep(100);}throw new Exception("object list did not stabilize within 3000 ms"); }
    static string CategorySelect(string path,out string before) { var tree=Unique("category tree","SysTreeView32",2093,"FaceClass");var list=Unique("object list","SysListView32",1041,"FaceClass");IntPtr old=(IntPtr)Msg(tree.Handle,0x110A,(IntPtr)9,IntPtr.Zero);before="{\"path\":"+J(TreePath(tree,old))+"}";IntPtr root=TreeRelated(tree,0,IntPtr.Zero),found;if(!FindTreePath(tree,root,PathParts(path),0,out found))throw new Exception("category path not found: "+path);if(Msg(tree.Handle,0x110B,(IntPtr)9,found)==0)throw new Exception("TVM_SELECTITEM failed");WaitListStable(list);IntPtr selected=(IntPtr)Msg(tree.Handle,0x110A,(IntPtr)9,IntPtr.Zero);if(selected!=found)throw new Exception("category selection readback did not match");return "{\"path\":"+J(TreePath(tree,selected))+",\"listCount\":"+Count(list)+"}"; }
    static int FindObjectRow(WindowInfo list,string editorId) { int count=Count(list),match=-1;for(int i=0;i<count;i++){if(ListCell(list,i)==editorId){if(match!=-1)throw new Exception("duplicate exact object rows: "+editorId);match=i;}}return match; }
    static string ObjectsFind(string editorId) { var list=Unique("object list","SysListView32",1041,"FaceClass");var tree=Unique("category tree","SysTreeView32",2093,"FaceClass");int row=FindObjectRow(list,editorId);return "{\"editorId\":"+J(editorId)+",\"found\":"+(row>=0).ToString().ToLower()+",\"row\":"+(row>=0?row.ToString():"null")+",\"category\":"+J(TreePath(tree,(IntPtr)Msg(tree.Handle,0x110A,(IntPtr)9,IntPtr.Zero)))+",\"listCount\":"+Count(list)+"}"; }
    static int SelectedRow(WindowInfo list) { return checked((int)Msg(list.Handle,0x100C,(IntPtr)(-1),(IntPtr)2)); }
    static void SetListState(WindowInfo list,int row,uint state,uint mask) { IntPtr process=OpenProcess(0x38,false,target);if(process==IntPtr.Zero)throw new Exception("OpenProcess failed for object selection");IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,(UIntPtr)64,0x3000,4);bool safe=true;try{if(memory==IntPtr.Zero)throw new Exception("selection buffer allocation failed");byte[] item=new byte[60];Array.Copy(BitConverter.GetBytes(state),0,item,12,4);Array.Copy(BitConverter.GetBytes(mask),0,item,16,4);UIntPtr n;if(!WriteProcessMemory(process,memory,item,(UIntPtr)item.Length,out n))throw new Exception("selection buffer write failed");try{Msg(list.Handle,0x102B,(IntPtr)row,memory);}catch{safe=false;throw;}}finally{if(memory!=IntPtr.Zero&&safe)VirtualFreeEx(process,memory,UIntPtr.Zero,0x8000);CloseHandle(process);} }
    static int ListState(WindowInfo list,int row,int mask) { return checked((int)Msg(list.Handle,0x102C,(IntPtr)row,(IntPtr)mask)); }
    static void SetChecked(WindowInfo list,int row,bool value) { uint state=value?0x2000u:0x1000u;SetListState(list,row,state,0xF000);if(ListState(list,row,0xF000)!=(int)state)throw new Exception("list checkbox readback failed for row "+row); }
    static string ObjectSelect(string editorId,out string before) { var list=Unique("object list","SysListView32",1041,"FaceClass");int old=SelectedRow(list);before="{\"row\":"+(old>=0?old.ToString():"null")+",\"editorId\":"+(old>=0?J(ListCell(list,old)):"null")+"}";int row=FindObjectRow(list,editorId);if(row<0)throw new Exception("object not found in current category/list: "+editorId);SetListState(list,-1,0,3);SetListState(list,row,3,3);int selected=SelectedRow(list);if(selected!=row||ListCell(list,selected)!=editorId)throw new Exception("object selection readback did not match");return "{\"row\":"+selected+",\"editorId\":"+J(ListCell(list,selected))+",\"selected\":true}"; }
    static string TopWindows() {var rows=new List<string>();foreach(var w in windows)if(w.Parent==IntPtr.Zero&&w.Visible)rows.Add(WindowJson(w));return "["+String.Join(",",rows.ToArray())+"]";}
    static void GuardPlugin() {if(MainWindow().Text.TrimEnd('*')!=ExpectedTitle())throw new Exception("unexpected plugin title: "+MainWindow().Text);}
    static void GuardDialogs() {foreach(var w in windows)if(w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&!IsPreview(w))throw new Exception("blocked by existing dialog: "+w.Text);if(!MainWindow().Enabled)throw new Exception("main window is disabled; possible modal blocker");}
    static uint FindMenuLabel(IntPtr menu,string label) {
        uint found=0;int count=GetMenuItemCount(menu);if(count<0)throw new Exception("resource menu unavailable");
        for(int i=0;i<count;i++){var text=new StringBuilder(1024);GetMenuString(menu,(uint)i,text,text.Capacity,0x400);IntPtr sub=GetSubMenu(menu,i);uint candidate=0;
            if(sub!=IntPtr.Zero)candidate=FindMenuLabel(sub,label);else if(text.ToString()==label)candidate=GetMenuItemID(menu,i);
            if(candidate!=0){if(found!=0)throw new Exception("ambiguous resource menu label");found=candidate;}}
        return found;
    }
    static readonly Dictionary<string,uint> resourceCache=new Dictionary<string,uint>();
    static uint ResourceCommand(string resource,string label) {
        uint cached;string key=target+"\0"+resource+"\0"+label;if(resourceCache.TryGetValue(key,out cached))return cached;
        uint id=ResourceCommandUncached(resource,label);resourceCache[key]=id;return id;
    }
    static uint ResourceCommandUncached(string resource,string label) {
        IntPtr module=LoadLibraryEx(GeckExecutable(),IntPtr.Zero,2);if(module==IntPtr.Zero)throw new Exception("resource load failed");
        IntPtr name=Marshal.StringToHGlobalUni(resource),menu=IntPtr.Zero;
        try{menu=LoadMenu(module,name);if(menu==IntPtr.Zero)throw new Exception("menu resource not found");uint id=FindMenuLabel(menu,label);if(id==0||id>65535)throw new Exception("command label not found");return id;}
        finally{if(menu!=IntPtr.Zero)DestroyMenu(menu);Marshal.FreeHGlobal(name);FreeLibrary(module);}
    }
    static void PostCommand(IntPtr owner,uint command,IntPtr control) {uint pid;GetWindowThreadProcessId(owner,out pid);if(pid!=target||!IsWindowEnabled(owner))throw new Exception("command owner unavailable or disabled");if(!PostMessage(owner,0x111,(IntPtr)command,control))throw new Exception("PostMessage failed: "+Marshal.GetLastWin32Error());}
    static WindowInfo IdentifiedDialog(string editorId) {
        var matches=new List<WindowInfo>();foreach(var w in windows){if(w.Parent!=IntPtr.Zero||!w.Visible||w.ClassName!="#32770")continue;
        if(windows.Exists(c=>c.ActualParent==w.Handle&&c.ClassName=="Edit"&&c.Id==5500&&c.Text==editorId))matches.Add(w);}
        if(matches.Count>1)throw new Exception("multiple record dialogs match identity");return matches.Count==1?matches[0]:null;
    }
    static string ObjectOpen(string editorId,out string before) {
        GuardPlugin();before="{\"windows\":"+TopWindows()+"}";var existing=IdentifiedDialog(editorId);if(existing!=null){CheckOtherDialogs(existing);return "{\"editorId\":"+J(editorId)+",\"dialog\":"+WindowJson(existing)+",\"alreadyOpen\":true}";}
        GuardDialogs();string selected;ObjectSelect(editorId,out selected);var list=Unique("object list","SysListView32",1041,"FaceClass");uint command=ResourceCommand("OBJPOPUP","Edit");
        PostCommand(list.ActualParent,command,IntPtr.Zero);var wait=Stopwatch.StartNew();
        while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();var dialog=IdentifiedDialog(editorId);if(dialog!=null)return "{\"editorId\":"+J(editorId)+",\"commandId\":"+command+",\"commandOwner\":"+list.ActualParent.ToInt64()+",\"dialog\":"+WindowJson(dialog)+"}";
            foreach(var w in windows)if(w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&!IsPreview(w))throw new Exception("unexpected dialog after record open: "+w.Text);
        }throw new Exception("record opening command dispatched but identified dialog did not appear; do not retry blindly");
    }
    static WindowInfo DialogControl(WindowInfo dialog,string cls,int id) {var matches=windows.FindAll(w=>w.ActualParent==dialog.Handle&&w.ClassName==cls&&w.Id==id);if(matches.Count!=1)throw new Exception("dialog control selector matched "+matches.Count+" controls: "+cls+"/"+id);return matches[0];}
    static string ObjectCancel(string editorId,out string before) {
        GuardPlugin();before="{\"windows\":"+TopWindows()+"}";var dialog=IdentifiedDialog(editorId);if(dialog==null)throw new Exception("identified record dialog not open");CheckOtherDialogs(dialog);var cancel=DialogControl(dialog,"Button",2);if(cancel.Text!="Cancel")throw new Exception("unexpected cancel control label");PostCommand(dialog.Handle,2,cancel.Handle);
        var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<3000){System.Threading.Thread.Sleep(100);Discover();if(!windows.Exists(w=>w.Handle==dialog.Handle&&w.Visible))return "{\"editorId\":"+J(editorId)+",\"cancelled\":true,\"windows\":"+TopWindows()+"}";}throw new Exception("record dialog did not close after cancel");
    }
    static bool IsPreview(WindowInfo w) {return w.Parent==IntPtr.Zero&&w.ClassName=="#32770"&&w.Text.StartsWith("Preview Object: '")&&windows.Exists(c=>c.ActualParent==w.Handle&&c.ClassName=="Button"&&c.Id==2&&c.Text=="Close")&&windows.Exists(c=>c.ActualParent==w.Handle&&c.ClassName=="SysListView32"&&c.Id==2416);}
    static WindowInfo IdentifiedPreview(string editorId) {var matches=windows.FindAll(w=>w.Visible&&IsPreview(w)&&w.Text.StartsWith("Preview Object: '"+editorId+"' ("));if(matches.Count>1)throw new Exception("multiple matching previews");return matches.Count==1?matches[0]:null;}
    static string PreviewOpen(string editorId,out string before) {
        GuardPlugin();GuardDialogs();before="{\"windows\":"+TopWindows()+"}";var existing=IdentifiedPreview(editorId);if(existing!=null)return "{\"editorId\":"+J(editorId)+",\"preview\":"+WindowJson(existing)+",\"alreadyOpen\":true,\"visualVerified\":false}";string selected;ObjectSelect(editorId,out selected);var list=Unique("object list","SysListView32",1041,"FaceClass");uint command=ResourceCommand("OBJPOPUP","Preview");PostCommand(list.ActualParent,command,IntPtr.Zero);
        var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();
            foreach(var w in windows)if(w.Visible&&IsPreview(w)&&w.Text.StartsWith("Preview Object: '"+editorId+"' ("))return "{\"editorId\":"+J(editorId)+",\"commandId\":"+command+",\"commandOwner\":"+list.ActualParent.ToInt64()+",\"preview\":"+WindowJson(w)+",\"visualVerified\":false}";
            foreach(var w in windows)if(w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&!IsPreview(w))throw new Exception("unexpected dialog after preview command: "+w.Text);
        }throw new Exception("preview command dispatched but identified preview did not appear; inspect windows before another attempt");
    }
    static void CheckOtherDialogs(WindowInfo allowed) {foreach(var w in windows)if(w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&!IsPreview(w)&&(allowed==null||w.Handle!=allowed.Handle))throw new Exception("blocked by unexpected dialog: "+w.Text);}
    static string ObjectRead(string editorId,out string before) {
        ObjectOpen(editorId,out before);var dialog=IdentifiedDialog(editorId);CheckOtherDialogs(dialog);
        if(dialog==null||dialog.Text!="Static")throw new Exception("expected identified Static dialog");
        var id=DialogControl(dialog,"Edit",5500);var model=DialogControl(dialog,"Edit",2421);
        return "{\"editorId\":"+J(Text(id.Handle))+",\"modelPath\":"+J(Text(model.Handle))+",\"dialogHandle\":"+dialog.Handle.ToInt64()+"}";
    }
    static string PreviewClose(string editorId,out string before) {
        GuardPlugin();before="{\"windows\":"+TopWindows()+"}";var preview=IdentifiedPreview(editorId);if(preview==null)throw new Exception("identified preview not open");CheckOtherDialogs(null);var button=DialogControl(preview,"Button",2);PostCommand(preview.Handle,2,button.Handle);
        var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<3000){System.Threading.Thread.Sleep(100);Discover();if(IdentifiedPreview(editorId)==null)return "{\"editorId\":"+J(editorId)+",\"closed\":true,\"windows\":"+TopWindows()+"}";}throw new Exception("preview did not close");
    }
    static WindowInfo OwnedDialog(WindowInfo owner,string title) {var matches=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Owner==owner.Handle&&w.Text==title);if(matches.Count>1)throw new Exception("multiple owned dialogs: "+title);return matches.Count==1?matches[0]:null;}
    static void GuardChain(params WindowInfo[] allowed) {foreach(var w in windows){if(w.Parent!=IntPtr.Zero||!w.Visible||w.ClassName!="#32770"||IsPreview(w))continue;bool match=false;foreach(var a in allowed)if(a!=null&&a.Handle==w.Handle)match=true;if(!match)throw new Exception("unexpected modal blocker: "+w.Text);}}
    static WindowInfo WaitOwned(WindowInfo owner,string title,params WindowInfo[] allowed) {var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();var found=OwnedDialog(owner,title);var chain=new List<WindowInfo>(allowed);chain.Add(found);GuardChain(chain.ToArray());if(found!=null)return found;}throw new Exception("expected dialog did not appear: "+title);}
    static void WaitClosed(WindowInfo closing,params WindowInfo[] allowed) {var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();var chain=new List<WindowInfo>(allowed);chain.Add(closing);GuardChain(chain.ToArray());if(!windows.Exists(w=>w.Handle==closing.Handle&&w.Visible))return;}throw new Exception("dialog did not close: "+closing.Text);}
    // ---- script editor (discovery + compile) ----
    static bool MenuHasId(IntPtr menu,uint id,int depth){if(menu==IntPtr.Zero||depth>6)return false;int n=GetMenuItemCount(menu);for(int i=0;i<n;i++){IntPtr sub=GetSubMenu(menu,i);if(sub!=IntPtr.Zero){if(MenuHasId(sub,id,depth+1))return true;}else if(GetMenuItemID(menu,i)==id)return true;}return false;}
    static WindowInfo ScriptEditor(){var m=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.Text!=null&&w.Text.StartsWith("Script Edit"));if(m.Count>1)throw new Exception("multiple script editor windows");return m.Count==1?m[0]:null;}
    static string ChildrenJson(WindowInfo top){var b=new StringBuilder("[");bool first=true;foreach(var w in windows){if(w.ActualParent!=top.Handle&&w.Parent!=top.Handle)continue;if(w.Handle==top.Handle)continue;if(!first)b.Append(',');first=false;string text=w.Text;if(text!=null&&text.Length>300)text=text.Substring(0,300)+"...";var c=new WindowInfo{Handle=w.Handle,Parent=w.Parent,ActualParent=w.ActualParent,Owner=w.Owner,ClassName=w.ClassName,Text=text,Id=w.Id,Visible=w.Visible,Enabled=w.Enabled};b.Append(WindowJson(c));}b.Append("]");return b.ToString();}
    static string TopWithChildren(){var b=new StringBuilder("[");bool first=true;foreach(var w in windows){if(w.Parent!=IntPtr.Zero||!w.Visible)continue;if(!first)b.Append(',');first=false;b.Append("{\"window\":"+WindowJson(w)+",\"children\":"+ChildrenJson(w)+"}");}b.Append("]");return b.ToString();}
    static string ScriptEditorOpen(out string before){
        before="{\"windows\":"+TopWindows()+"}";var existing=ScriptEditor();
        if(existing==null){GuardDialogs();uint cmd=ResourceCommand("MAINMENU","&Edit Scripts...");PostCommand(MainWindow().Handle,cmd,IntPtr.Zero);var wait=Stopwatch.StartNew();
            while(wait.ElapsedMilliseconds<8000){System.Threading.Thread.Sleep(150);Discover();existing=ScriptEditor();if(existing!=null)break;}
            if(existing==null)throw new Exception("script editor did not appear");System.Threading.Thread.Sleep(300);Discover();existing=ScriptEditor();}
        return "{\"editor\":"+WindowJson(existing)+",\"top\":"+TopWithChildren()+"}";}
    static string ScriptEditorCommand(string label,out string before){
        var allowed=new List<string>{"&Open...","&Save","E&xit","&Previous Script","N&ext Script"};if(!allowed.Contains(label))throw new Exception("script editor command not allowed: "+label);
        var editor=ScriptEditor();if(editor==null)throw new Exception("script editor is not open");before="{\"top\":"+TopWithChildren()+"}";
        uint cmd=ResourceCommand("SCRIPTEDITMENU",label);PostCommand(editor.Handle,cmd,IntPtr.Zero);System.Threading.Thread.Sleep(1500);Discover();
        return "{\"commandId\":"+cmd+",\"top\":"+TopWithChildren()+"}";}
    static WindowInfo OwnedBy(WindowInfo owner,string title){var m=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Owner==owner.Handle&&(title==null||w.Text==title));if(m.Count>1)throw new Exception("multiple owned dialogs: "+title);return m.Count==1?m[0]:null;}
    static string DialogTexts(WindowInfo d){var parts=new List<string>();foreach(var c in windows)if(c.Parent==d.Handle&&(c.ClassName=="Static"||c.ClassName=="Edit")&&!String.IsNullOrEmpty(c.Text))parts.Add(c.Text);return String.Join(" | ",parts.ToArray());}
    static string ScriptCompile(string editorId,out string before){
        before="{\"top\":"+TopWindows()+"}";string ignored;ScriptEditorOpen(out ignored);Discover();var editor=ScriptEditor();if(editor==null)throw new Exception("script editor unavailable");
        foreach(var w in windows)if(w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Handle!=editor.Handle&&!(w.Owner==editor.Handle&&w.Text=="Select Form")&&!IsPreview(w))throw new Exception("blocked by existing dialog: "+w.Text);
        var select=OwnedBy(editor,"Select Form");
        if(select==null){PostCommand(editor.Handle,ResourceCommand("SCRIPTEDITMENU","&Open..."),IntPtr.Zero);var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<8000&&select==null){System.Threading.Thread.Sleep(150);Discover();select=OwnedBy(editor,"Select Form");}if(select==null)throw new Exception("Select Form dialog did not appear");}
        var lists=windows.FindAll(w=>w.Parent==select.Handle&&w.ClassName=="SysListView32"&&w.Id==1018);if(lists.Count!=1)throw new Exception("script list selector matched "+lists.Count);var list=lists[0];
        int row=-1,count=Count(list);for(int i=0;i<count;i++)if(ListCell(list,i)==editorId){if(row!=-1)throw new Exception("duplicate script rows: "+editorId);row=i;}
        if(row<0){PostMessage(select.Handle,0x111,(IntPtr)2,IntPtr.Zero);throw new Exception("script not found in Select Form list ("+count+" rows): "+editorId);}
        SetListState(list,-1,0,3);SetListState(list,row,3,3);if(SelectedRow(list)!=row)throw new Exception("script selection readback failed");
        if(!PostMessage(select.Handle,0x111,(IntPtr)1,IntPtr.Zero))throw new Exception("PostMessage IDOK failed");
        var w2=Stopwatch.StartNew();while(w2.ElapsedMilliseconds<8000){System.Threading.Thread.Sleep(150);Discover();if(OwnedBy(editor,"Select Form")==null)break;}
        if(OwnedBy(editor,"Select Form")!=null)throw new Exception("Select Form did not close");
        var edits=windows.FindAll(w=>w.Parent==editor.Handle&&w.ClassName=="RichEdit20A"&&w.Id==1166);if(edits.Count!=1)throw new Exception("script text control matched "+edits.Count);
        string text=Text(edits[0].Handle);string firstLine=text.Split('\n')[0].Trim();
        if(firstLine.IndexOf(editorId,StringComparison.OrdinalIgnoreCase)<0)throw new Exception("loaded script text does not start with its name: "+firstLine);
        PostCommand(editor.Handle,ResourceCommand("SCRIPTEDITMENU","&Save"),IntPtr.Zero);
        var errors=new List<string>();var w3=Stopwatch.StartNew();int quiet=0;
        while(w3.ElapsedMilliseconds<15000){System.Threading.Thread.Sleep(200);Discover();WindowInfo blocker=null;
            foreach(var w in windows)if(w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Handle!=editor.Handle&&!IsPreview(w)){blocker=w;break;}
            if(blocker!=null){quiet=0;errors.Add(blocker.Text+": "+DialogTexts(blocker));if(errors.Count>30)throw new Exception("too many compile dialogs");PostMessage(blocker.Handle,0x111,(IntPtr)1,IntPtr.Zero);System.Threading.Thread.Sleep(300);continue;}
            quiet++;if(quiet>=10)break;}
        return "{\"editorId\":"+J(editorId)+",\"row\":"+row+",\"firstLine\":"+J(firstLine)+",\"textLength\":"+text.Length+",\"compiled\":"+(errors.Count==0).ToString().ToLower()+",\"errors\":["+JoinJ(errors)+"],\"mainTitle\":"+J(MainWindow().Text)+"}";}
    static string ScriptEditorClose(out string before){
        before="{\"top\":"+TopWindows()+"}";var editor=ScriptEditor();if(editor==null)return "{\"closed\":false,\"wasOpen\":false}";
        var select=OwnedBy(editor,"Select Form");if(select!=null){PostMessage(select.Handle,0x111,(IntPtr)2,IntPtr.Zero);var w=Stopwatch.StartNew();while(w.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(150);Discover();if(OwnedBy(editor,"Select Form")==null)break;}}
        Discover();editor=ScriptEditor();if(editor==null)return "{\"closed\":true}";
        PostCommand(editor.Handle,ResourceCommand("SCRIPTEDITMENU","E&xit"),IntPtr.Zero);var w2=Stopwatch.StartNew();
        while(w2.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(150);Discover();if(ScriptEditor()==null)return "{\"closed\":true}";
            foreach(var d in windows)if(d.Parent==IntPtr.Zero&&d.Visible&&d.ClassName=="#32770"&&d.Owner==editor.Handle)throw new Exception("dialog while closing script editor: "+d.Text+": "+DialogTexts(d));}
        throw new Exception("script editor did not close");}
    static string JoinJ(List<string> items){var b=new StringBuilder();for(int i=0;i<items.Count;i++){if(i>0)b.Append(',');b.Append(J(items[i]));}return b.ToString();}
    static string ScriptEditorInspect(){return "{\"editor\":"+(ScriptEditor()==null?"null":WindowJson(ScriptEditor()))+",\"top\":"+TopWithChildren()+"}";}
    static void ButtonCommand(WindowInfo dialog,int id,string label) {var button=DialogControl(dialog,"Button",id);if(button.Text!=label||!button.Enabled)throw new Exception("button label/state mismatch: "+label);PostCommand(dialog.Handle,(uint)id,button.Handle);}
    static string ObjectSetModel(string editorId,string modelPath,out string before) {
        GuardPlugin();before=null;
        GuardRecord(editorId);
        if(String.IsNullOrEmpty(modelPath)||modelPath.IndexOf('/')>=0||modelPath.IndexOf(':')>=0||modelPath.StartsWith("\\")||modelPath.Contains("..")||modelPath.StartsWith("meshes\\",StringComparison.OrdinalIgnoreCase)||!modelPath.EndsWith(".nif",StringComparison.OrdinalIgnoreCase))throw new Exception("model must be a .nif path relative to Data\\meshes");
        string game=System.IO.Path.GetDirectoryName(GeckExecutable());
        string asset=System.IO.Path.Combine(game,"Data\\meshes\\"+modelPath);if(!System.IO.File.Exists(asset))throw new Exception("model file not found: "+asset);
        var record=IdentifiedDialog(editorId);if(record==null){string opened;ObjectOpen(editorId,out opened);record=IdentifiedDialog(editorId);}
        string previous=Text(DialogControl(record,"Edit",2421).Handle);before="{\"editorId\":"+J(editorId)+",\"modelPath\":"+J(previous)+",\"windows\":"+TopWindows()+"}";
        var model=OwnedDialog(record,"Model Data");var file=model==null?null:OwnedDialog(model,"Select File");GuardChain(record,model,file);
        string expectedOld=Config("EXPECTED_MODEL", "");
        if(expectedOld!=""&&previous!=expectedOld)throw new Exception("STALE_STATE: previous model differs from expected value");
        if(previous==modelPath&&model==null)return "{\"changed\":false,\"committed\":false,\"reopenedVerified\":false,\"pluginSaved\":false,\"modelPath\":"+J(previous)+"}";
        if(model==null){ButtonCommand(record,2420,"Edit");model=WaitOwned(record,"Model Data",record);}
        if(file==null){ButtonCommand(model,2420,"Edit");file=WaitOwned(model,"Select File",record,model);}
        var names=windows.FindAll(w=>w.Parent==file.Handle&&w.ClassName=="Edit"&&w.Id==1148&&w.Visible&&w.Enabled);if(names.Count!=1)throw new Exception("filename edit selector ambiguous");
        var parent=windows.Find(w=>w.Handle==names[0].ActualParent);if(parent==null||parent.ClassName!="ComboBox"||parent.Id!=1148)throw new Exception("filename edit parent mismatch");
        SetText(names[0],asset);if(Text(names[0].Handle)!=asset)throw new Exception("file chooser path readback mismatch");ButtonCommand(file,1,"&Open");WaitClosed(file,record,model);
        string loaded=Text(DialogControl(model,"Edit",2421).Handle);if(!String.Equals(loaded,modelPath,StringComparison.Ordinal))throw new Exception("loaded model path readback mismatch: "+loaded);
        ButtonCommand(model,1,"OK");WaitClosed(model,record);
        if(Text(DialogControl(record,"Edit",2421).Handle)!=modelPath)throw new Exception("record model field mismatch after Model Data commit");
        ButtonCommand(record,1,"OK");WaitClosed(record);string ignored;string reopened=ObjectRead(editorId,out ignored);
        if(Text(DialogControl(IdentifiedDialog(editorId),"Edit",2421).Handle)!=modelPath)throw new Exception("model path did not persist after commit/reopen; plugin was not saved");
        return "{\"record\":"+reopened+",\"committed\":true,\"reopenedVerified\":true,\"pluginSaved\":false,\"windows\":"+TopWindows()+"}";
    }
    static string ModelInspect(string editorId,out string before) {
        before=ObjectRead(editorId,out before);var dialog=IdentifiedDialog(editorId);CheckOtherDialogs(dialog);var edit=DialogControl(dialog,"Button",2420);if(edit.Text!="Edit")throw new Exception("unexpected model Edit label");PostCommand(dialog.Handle,2420,edit.Handle);
        var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<4000){System.Threading.Thread.Sleep(100);Discover();foreach(var w in windows)if(w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Handle!=dialog.Handle){return Inspect(200);}}throw new Exception("model Edit produced no dialog");
    }
    static WindowInfo ModelDialog(string editorId) {var record=IdentifiedDialog(editorId);if(record==null)throw new Exception("record dialog absent");var matches=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Text=="Model Data"&&w.Owner==record.Handle);if(matches.Count!=1)throw new Exception("Model Data dialog selector matched "+matches.Count);return matches[0];}
    static string ModelBrowse(string editorId,out string before) {GuardPlugin();before="{\"windows\":"+TopWindows()+"}";var model=ModelDialog(editorId);var edit=DialogControl(model,"Button",2420);if(edit.Text!="Edit")throw new Exception("unexpected browse label");PostCommand(model.Handle,2420,edit.Handle);System.Threading.Thread.Sleep(300);Discover();return Inspect(250);}
    static string PluginPath() {GuardPlugin();string game=System.IO.Path.GetDirectoryName(GeckExecutable());string path=System.IO.Path.Combine(game,"Data\\"+ExpectedPlugin());if(!System.IO.File.Exists(path))throw new Exception("expected plugin file is absent");return path;}
    static string HashFile(string path) {using(var input=System.IO.File.OpenRead(path))using(var hash=System.Security.Cryptography.SHA256.Create()){return BitConverter.ToString(hash.ComputeHash(input)).Replace("-","").ToLowerInvariant();}}
    static string FileState(string path) {var info=new System.IO.FileInfo(path);return "{\"path\":"+J(path)+",\"size\":"+info.Length+",\"modifiedUtc\":"+J(info.LastWriteTimeUtc.ToString("o"))+",\"sha256\":"+J(HashFile(path))+"}";}
    static string PluginInspect() {return "{\"file\":"+FileState(PluginPath())+",\"editorTitle\":"+J(MainWindow().Text)+",\"unsavedChanges\":"+MainWindow().Text.EndsWith("*").ToString().ToLower()+"}";}
    static string PluginSave(string expectedHash,out string before) {
        GuardPlugin();GuardDialogs();string path=PluginPath();before="{\"file\":"+FileState(path)+",\"windows\":"+TopWindows()+"}";
        if(!MainWindow().Text.EndsWith("*"))throw new Exception("plugin has no indicated unsaved changes; no save dispatched");
        if(HashFile(path)!=expectedHash)throw new Exception("plugin changed after pre-save backup; no save dispatched");string old=FileState(path);uint command=ResourceCommand("MAINMENU","&Save");PostCommand(MainWindow().Handle,command,IntPtr.Zero);
        var wait=Stopwatch.StartNew();string previous=null;int stable=0;
        while(wait.ElapsedMilliseconds<10000){System.Threading.Thread.Sleep(200);Discover();GuardDialogs();string current=FileState(path);stable=current==previous?stable+1:0;previous=current;
            if(current!=old&&stable>=3&&!MainWindow().Text.EndsWith("*"))return "{\"file\":"+current+",\"commandId\":"+command+",\"fileWriteObserved\":true,\"persistenceVerified\":false,\"windows\":"+TopWindows()+"}";
        }throw new Exception("save dispatched but stable file write and clean editor state not both observed; inspect disk before retry");
    }
    static string WorldCellsInspect(out string before) {
        GuardPlugin();GuardDialogs();before="{\"windows\":"+TopWindows()+"}";
        uint command=ResourceCommand("MAINMENU","&Cells...");PostCommand(MainWindow().Handle,command,IntPtr.Zero);
        var wait=Stopwatch.StartNew();
        while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();
            var dialogs=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&!IsPreview(w));
            if(dialogs.Count==1)return "{\"commandId\":"+command+",\"dialog\":"+WindowJson(dialogs[0])+",\"inventory\":"+Inspect(500)+"}";
            if(dialogs.Count>1)throw new Exception("Cells command produced multiple dialogs; inspect before retry");
        }throw new Exception("Cells command dispatched but no dialog appeared; inspect before retry");
    }
    static string WorldCellsNewInspect(out string before) {
        GuardPlugin();var dialog=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Text=="Cell"&&w.Owner==MainWindow().Handle);
        if(dialog.Count!=1)throw new Exception("Cell dialog selector matched "+dialog.Count+" windows");
        var list=DialogControl(dialog[0],"SysListView32",2064);int count=Count(list);before="{\"cellCount\":"+count+",\"windows\":"+TopWindows()+"}";
        PostCommand(dialog[0].Handle,249,IntPtr.Zero);var wait=Stopwatch.StartNew();
        while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();
            var rediscovered=windows.Find(w=>w.Handle==list.Handle);var extra=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Handle!=dialog[0].Handle&&!IsPreview(w));
            if(extra.Count>0||(rediscovered!=null&&Count(rediscovered)!=count)||MainWindow().Text.EndsWith("*"))return "{\"stateChanged\":true,\"inventory\":"+Inspect(500)+"}";
        }throw new Exception("Cell dialog New command produced no identified state change");
    }
    static WindowInfo CellView() {
        var matches=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="ViewerClass"&&w.Text=="Cell View");
        if(matches.Count!=1)throw new Exception("Cell View selector matched "+matches.Count+" windows");return matches[0];
    }
    static WindowInfo CellViewControl(WindowInfo view,string cls,int id) {
        var matches=windows.FindAll(w=>w.ActualParent==view.Handle&&w.ClassName==cls&&w.Id==id);
        if(matches.Count!=1)throw new Exception("Cell View control selector matched "+matches.Count+" controls: "+cls+"/"+id);return matches[0];
    }
    static string CellDialogCancel(out string before) {
        GuardPlugin();var matches=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Text=="Cell"&&w.Owner==MainWindow().Handle);
        if(matches.Count!=1)throw new Exception("Cell dialog selector matched "+matches.Count+" windows");var dialog=matches[0];before="{\"dialog\":"+WindowJson(dialog)+"}";
        ButtonCommand(dialog,2,"Cancel");WaitClosed(dialog);return "{\"cancelled\":true,\"windows\":"+TopWindows()+"}";
    }
    static string CellSelect(string editorId,out string before) {
        GuardPlugin();GuardDialogs();var view=CellView();var list=CellViewControl(view,"SysListView32",1155);var label=CellViewControl(view,"Static",1163);
        int old=SelectedRow(list),row=-1;for(int i=0;i<Count(list);i++){string value=ListCell(list,i);if(value==editorId||value==editorId+" *"){if(row!=-1)throw new Exception("duplicate cell rows: "+editorId);row=i;}}before="{\"row\":"+(old>=0?old.ToString():"null")+",\"editorId\":"+(old>=0?J(ListCell(list,old)):"null")+",\"objectsLabel\":"+J(Text(label.Handle))+"}";
        if(row<0)throw new Exception("cell not found in current Cell View list: "+editorId);SetListState(list,-1,0,3);SetListState(list,row,3,3);
        var wait=Stopwatch.StartNew();string expected=editorId+" Objects";while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();view=CellView();label=CellViewControl(view,"Static",1163);if(Text(label.Handle)==expected){list=CellViewControl(view,"SysListView32",1155);int selected=SelectedRow(list);string selectedText=selected>=0?ListCell(list,selected):null;if(selected!=row||(selectedText!=editorId&&selectedText!=editorId+" *"))throw new Exception("cell selection readback did not match");return "{\"row\":"+selected+",\"editorId\":"+J(editorId)+",\"objectsLabel\":"+J(Text(label.Handle))+",\"referenceCount\":"+Count(CellViewControl(view,"SysListView32",1156))+"}";}}
        throw new Exception("cell row selected but Cell View did not load it within 5 seconds");
    }
    static string CellFind(string text) {
        GuardPlugin();GuardDialogs();var view=CellView();var list=CellViewControl(view,"SysListView32",1155);int count=Count(list);var rows=new List<string>();
        for(int i=0;i<count;i++){string value=ListCell(list,i);if(value.IndexOf(text,StringComparison.OrdinalIgnoreCase)>=0)rows.Add("{\"row\":"+i+",\"editorId\":"+J(value)+"}");}
        return "{\"query\":"+J(text)+",\"cellCount\":"+count+",\"matches\":["+String.Join(",",rows.ToArray())+"]}";
    }
    static string CellLoad(string editorId,out string before) {
        if(editorId!="SalvatoreTestCell")throw new Exception("cell loading is limited to SalvatoreTestCell");GuardPlugin();GuardDialogs();var view=CellView();var list=CellViewControl(view,"SysListView32",1155);int row=-1;for(int i=0;i<Count(list);i++){string value=ListCell(list,i);if(value==editorId||value==editorId+" *")row=i;}if(row<0)throw new Exception("SalvatoreTestCell not found");
        SetListState(list,-1,0,3);SetListState(list,row,3,3);Msg(list.Handle,0x1013,(IntPtr)row,(IntPtr)1);RECT item=ListItemRect(list,row);var point=new POINT{X=item.Left+Math.Max(8,Math.Min(40,(item.Right-item.Left)/3)),Y=(item.Top+item.Bottom)/2};if(!ClientToScreen(list.Handle,ref point))throw new Exception("cell-load coordinates unavailable");before="{\"cell\":"+J(editorId)+",\"row\":"+row+",\"point\":{\"x\":"+point.X+",\"y\":"+point.Y+"}}";
        if(!SetForegroundWindow(view.Handle)||!SetCursorPos(point.X,point.Y))throw new Exception("Cell View could not be activated for load");System.Threading.Thread.Sleep(150);for(int i=0;i<2;i++){mouse_event(0x0002,0,0,0,UIntPtr.Zero);System.Threading.Thread.Sleep(60);mouse_event(0x0004,0,0,0,UIntPtr.Zero);System.Threading.Thread.Sleep(100);}System.Threading.Thread.Sleep(1200);Discover();view=CellView();var label=CellViewControl(view,"Static",1163);if(Text(label.Handle)!=editorId+" Objects")throw new Exception("cell load readback label did not match");return "{\"cell\":"+J(editorId)+",\"loaded\":true,\"objectsLabel\":"+J(Text(label.Handle))+",\"referenceCount\":"+Count(CellViewControl(view,"SysListView32",1156))+"}";
    }
    static string HeaderText(IntPtr header,int index) {
        // HDM_GETITEMW with a 32-bit HDITEMW (48 bytes) in GECK's address space; HDI_TEXT = 0x2.
        IntPtr process=OpenProcess(0x38,false,target);if(process==IntPtr.Zero)throw new Exception("OpenProcess failed for list header");
        IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,(UIntPtr)1024,0x3000,4);bool safe=true;
        try{if(memory==IntPtr.Zero)throw new Exception("header buffer allocation failed");byte[] item=new byte[48];
            Array.Copy(BitConverter.GetBytes(2),0,item,0,4);Array.Copy(BitConverter.GetBytes(memory.ToInt32()+64),0,item,8,4);Array.Copy(BitConverter.GetBytes(256),0,item,16,4);
            UIntPtr n;if(!WriteProcessMemory(process,memory,item,(UIntPtr)item.Length,out n))throw new Exception("header buffer write failed");
            try{Msg(header,0x120B,(IntPtr)index,memory);}catch{safe=false;throw;}
            byte[] text=new byte[512];if(!ReadProcessMemory(process,(IntPtr)(memory.ToInt32()+64),text,(UIntPtr)text.Length,out n))throw new Exception("header buffer read failed");
            return Encoding.Unicode.GetString(text).Split('\0')[0];}
        finally{if(memory!=IntPtr.Zero&&safe)VirtualFreeEx(process,memory,UIntPtr.Zero,0x8000);CloseHandle(process);}
    }
    static string[] ListHeaders(WindowInfo list) {
        IntPtr header=(IntPtr)Msg(list.Handle,0x101F,IntPtr.Zero,IntPtr.Zero);if(header==IntPtr.Zero)return new string[]{"column0"};
        int count=checked((int)Msg(header,0x1200,IntPtr.Zero,IntPtr.Zero));if(count<1||count>32)throw new Exception("unexpected list column count "+count);
        var names=new string[count];for(int c=0;c<count;c++)names[c]=HeaderText(header,c);return names;
    }
    static string CellRefs(string editorId,out string before) {
        string selected=CellSelect(editorId,out before);Discover();
        var refs=CellViewControl(CellView(),"SysListView32",1156);int count=Count(refs);if(count>5000)throw new Exception("reference list exceeds limit");
        string[] headers=ListHeaders(refs);var rows=new List<string>();
        for(int i=0;i<count;i++){var cells=new List<string>();for(int c=0;c<headers.Length;c++)cells.Add(J(ListColumn(refs,i,c)));rows.Add("["+String.Join(",",cells.ToArray())+"]");}
        var names=new List<string>();foreach(var h in headers)names.Add(J(h));
        return "{\"cell\":"+J(editorId)+",\"selection\":"+selected+",\"columns\":["+String.Join(",",names.ToArray())+"],\"count\":"+count+",\"rows\":["+String.Join(",",rows.ToArray())+"]}";
    }
    static int FindRefRow(WindowInfo refs,uint formId) {
        // Match the reference whose row contains its FormID in any column (hex, with or without leading zeros).
        int columns=ListHeaders(refs).Length,count=Count(refs),match=-1;
        for(int i=0;i<count;i++)for(int c=0;c<columns;c++){string cell=ListColumn(refs,i,c).Trim();uint value;
            if(cell.Length>=3&&cell.Length<=8&&UInt32.TryParse(cell,System.Globalization.NumberStyles.HexNumber,null,out value)&&value==formId){if(match!=-1&&match!=i)throw new Exception("FormID matched several reference rows");match=i;}}
        return match;
    }
    static string CellShow(string editorId,string formText,out string before) {
        uint formId;if(formText.Length!=8||!UInt32.TryParse(formText,System.Globalization.NumberStyles.HexNumber,null,out formId))throw new Exception("cell.show needs an 8-digit hex FormID");
        GuardPlugin();GuardDialogs();before=CellSelect(editorId,out before);
        var view=CellView();var list=CellViewControl(view,"SysListView32",1155);int row=SelectedRow(list);
        Msg(list.Handle,0x1013,(IntPtr)row,(IntPtr)1);RECT rect=ListItemRect(list,row);
        IntPtr pt=(IntPtr)((((rect.Top+rect.Bottom)/2)<<16)|((rect.Left+40)&0xffff));
        // Posted, not sent: loading a cell with actors blocks GECK longer than the 500 ms send timeout.
        PostMessage(list.Handle,0x201,(IntPtr)1,pt);PostMessage(list.Handle,0x202,IntPtr.Zero,pt);
        PostMessage(list.Handle,0x203,(IntPtr)1,pt);PostMessage(list.Handle,0x202,IntPtr.Zero,pt);
        var wait=Stopwatch.StartNew();WindowInfo render=null;
        while(wait.ElapsedMilliseconds<15000){System.Threading.Thread.Sleep(250);Discover();
            var found=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="MonitorClass"&&w.Text.StartsWith(editorId+" ["));
            if(found.Count==1){render=found[0];break;}}
        if(render==null)throw new Exception("Render Window did not load "+editorId+" within 15 s");
        var refs=CellViewControl(CellView(),"SysListView32",1156);int refRow=FindRefRow(refs,formId);
        if(refRow<0)throw new Exception("reference "+formText+" not found in "+editorId);
        SetListState(refs,-1,0,3);SetListState(refs,refRow,3,3);Msg(refs.Handle,0x1013,(IntPtr)refRow,(IntPtr)1);
        RECT rr=ListItemRect(refs,refRow);IntPtr rp=(IntPtr)((((rr.Top+rr.Bottom)/2)<<16)|((rr.Left+25)&0xffff));
        PostMessage(refs.Handle,0x201,(IntPtr)1,rp);PostMessage(refs.Handle,0x202,IntPtr.Zero,rp);PostMessage(refs.Handle,0x203,(IntPtr)1,rp);PostMessage(refs.Handle,0x202,IntPtr.Zero,rp);
        System.Threading.Thread.Sleep(1500);Discover();
        refs=CellViewControl(CellView(),"SysListView32",1156);int selected=SelectedRow(refs);
        if(selected!=refRow)throw new Exception("reference selection readback did not match");
        return "{\"cell\":"+J(editorId)+",\"formId\":"+J(formText)+",\"row\":"+selected+",\"references\":"+Count(refs)+",\"renderTitle\":"+J(render.Text)+",\"visualVerified\":false,\"windows\":"+TopWindows()+"}";
    }
    // ---- Render Window camera/presentation (photo workflow) -------------------------------
    // Steps are a whitelisted, bounded ';'-separated list. zoom/key/click/redraw are posted window
    // messages (no global input). orbit/pan use real input inside the bottle: Wine SendInput for Shift
    // and mouse_event relative moves, which briefly moves the macOS cursor over the Render Window.
    static WindowInfo RenderWindowFor(string cell) {
        var found=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="MonitorClass"&&w.Text.StartsWith(cell+" ["));
        if(found.Count!=1)throw new Exception("Render Window for "+cell+" matched "+found.Count+" windows");return found[0];
    }
    static void ShiftKey(bool down) {var i=new KEYINPUT[1];i[0].Type=1;i[0].Vk=0x10;i[0].Flags=down?0u:2u;SendInput(1,i,Marshal.SizeOf(typeof(KEYINPUT)));}
    static int Bounded(string text,int limit,string what){int v;if(!Int32.TryParse(text,out v)||Math.Abs(v)>limit)throw new Exception(what+" must be an integer within +/-"+limit);return v;}
    static string RenderSteps(string cell,string steps,out string before) {
        GuardPlugin();GuardDialogs();var render=RenderWindowFor(cell);var h=render.Handle;
        RECT cr;GetClientRect(h,out cr);before="{\"title\":"+J(render.Text)+",\"client\":["+(cr.Right-cr.Left)+","+(cr.Bottom-cr.Top)+"]}";
        var parts=steps.Split(';');if(parts.Length>40)throw new Exception("at most 40 render steps");var done=new List<string>();
        bool shiftHeld=false,middleHeld=false;
        try {
        foreach(var raw in parts){var step=raw.Trim();if(step.Length==0)continue;var a=step.Split(':');string op=a[0];
            GetClientRect(h,out cr);int cx=(cr.Right-cr.Left)/2,cy=(cr.Bottom-cr.Top)/2;
            if(op=="max"&&a.Length==1){ShowWindow(h,3);}
            else if(op=="restore"&&a.Length==1){ShowWindow(h,9);}
            else if(op=="size"&&a.Length==3){int w=Bounded(a[1],8000,"width"),ht=Bounded(a[2],8000,"height");if(w<200||ht<200)throw new Exception("size too small");ShowWindow(h,9);if(!SetWindowPos(h,IntPtr.Zero,0,0,w,ht,0x0004|0x0002))throw new Exception("render resize failed");}
            else if(op=="redraw"&&a.Length==1){InvalidateRect(h,IntPtr.Zero,false);PostMessage(h,0x200,IntPtr.Zero,(IntPtr)((cy<<16)|(cx&0xffff)));}
            else if(op=="zoom"&&a.Length==2){int n=Bounded(a[1],60,"zoom");POINT p=new POINT{X=cx,Y=cy};ClientToScreen(h,ref p);
                for(int i=0;i<Math.Abs(n);i++){PostMessage(h,0x20A,(IntPtr)(((n>0?120:-120)&0xffff)<<16),(IntPtr)(((p.Y&0xffff)<<16)|(p.X&0xffff)));System.Threading.Thread.Sleep(60);}}
            else if(op=="key"&&a.Length==2&&a[1].Length==1&&Char.IsLetter(a[1][0])){int vk=(int)Char.ToUpper(a[1][0]);
                PostMessage(h,0x100,(IntPtr)vk,(IntPtr)1);PostMessage(h,0x102,(IntPtr)(int)Char.ToLower(a[1][0]),(IntPtr)1);PostMessage(h,0x101,(IntPtr)vk,unchecked((IntPtr)(int)0xC0000001));}
            else if(op=="click"&&a.Length==3){int x=Bounded(a[1],8000,"x"),y=Bounded(a[2],8000,"y");if(x<0||y<0||x>=cr.Right||y>=cr.Bottom)throw new Exception("click outside Render Window client area");
                IntPtr pt=(IntPtr)(((y&0xffff)<<16)|(x&0xffff));PostMessage(h,0x200,IntPtr.Zero,pt);PostMessage(h,0x201,(IntPtr)1,pt);System.Threading.Thread.Sleep(60);PostMessage(h,0x202,IntPtr.Zero,pt);}
            else if(op=="realclick"&&a.Length==3){int x=Bounded(a[1],8000,"x"),y=Bounded(a[2],8000,"y");if(x<0||y<0||x>=cr.Right||y>=cr.Bottom)throw new Exception("click outside Render Window client area");
                SetForegroundWindow(h);/* returns false when another macOS app is frontmost; Wine input still reaches GECK */System.Threading.Thread.Sleep(150);POINT p=new POINT{X=x,Y=y};ClientToScreen(h,ref p);if(!SetCursorPos(p.X,p.Y))throw new Exception("cursor positioning failed");
                System.Threading.Thread.Sleep(80);mouse_event(0x0002,0,0,0,UIntPtr.Zero);System.Threading.Thread.Sleep(60);mouse_event(0x0004,0,0,0,UIntPtr.Zero);}
            else if((op=="orbit"||op=="pan")&&a.Length==3){int dx=Bounded(a[1],3000,"dx"),dy=Bounded(a[2],3000,"dy");
                SetForegroundWindow(h);/* returns false when another macOS app is frontmost; Wine input still reaches GECK */System.Threading.Thread.Sleep(200);
                POINT p=new POINT{X=cx,Y=cy};ClientToScreen(h,ref p);if(!SetCursorPos(p.X,p.Y))throw new Exception("cursor positioning failed");System.Threading.Thread.Sleep(100);
                if(op=="orbit"){ShiftKey(true);shiftHeld=true;}else{mouse_event(0x0020,0,0,0,UIntPtr.Zero);middleHeld=true;}
                System.Threading.Thread.Sleep(100);int n=Math.Max(1,Math.Max(Math.Abs(dx),Math.Abs(dy))/6),sx=0,sy=0;
                for(int i=1;i<=n;i++){int tx=dx*i/n,ty=dy*i/n;mouse_event(0x0001,unchecked((uint)(tx-sx)),unchecked((uint)(ty-sy)),0,UIntPtr.Zero);sx=tx;sy=ty;System.Threading.Thread.Sleep(25);}
                System.Threading.Thread.Sleep(100);
                if(op=="orbit"){ShiftKey(false);shiftHeld=false;}else{mouse_event(0x0040,0,0,0,UIntPtr.Zero);middleHeld=false;}}
            else if(op=="sleep"&&a.Length==2){int ms=Bounded(a[1],10000,"sleep");if(ms<0)throw new Exception("sleep must be positive");System.Threading.Thread.Sleep(ms);}
            else throw new Exception("unsupported render step: "+step);
            done.Add(J(step));System.Threading.Thread.Sleep(120);}
        } finally {if(shiftHeld)ShiftKey(false);if(middleHeld)mouse_event(0x0040,0,0,0,UIntPtr.Zero);}
        System.Threading.Thread.Sleep(200);Discover();render=RenderWindowFor(cell);RECT wr;GetWindowRect(render.Handle,out wr);GetClientRect(render.Handle,out cr);
        return "{\"title\":"+J(render.Text)+",\"client\":["+(cr.Right-cr.Left)+","+(cr.Bottom-cr.Top)+"],\"windowRect\":["+wr.Left+","+wr.Top+","+wr.Right+","+wr.Bottom+"],\"steps\":["+String.Join(",",done.ToArray())+"],\"shiftDown\":"+((GetAsyncKeyState(0x10)&0x8000)!=0).ToString().ToLower()+",\"visualVerified\":false}";
    }
    static string MainRaise() {GuardPlugin();GuardDialogs();var main=MainWindow();if(!SetForegroundWindow(main.Handle))throw new Exception("GECK main window could not be raised");return "{\"raised\":true,\"window\":"+WindowJson(main)+"}";}
    static string PlacementLayout() {
        GuardPlugin();GuardDialogs();var objectWindow=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="FaceClass"&&w.Text=="Object Window");var render=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="MonitorClass"&&w.Text=="Render Window");var cell=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="ViewerClass"&&w.Text=="Cell View");
        if(objectWindow.Count!=1||render.Count!=1||cell.Count!=1)throw new Exception("placement window selectors were not unique");uint flags=0x0014;
        if(!SetWindowPos(objectWindow[0].Handle,IntPtr.Zero,25,75,350,190,flags)||!SetWindowPos(render[0].Handle,IntPtr.Zero,25,280,350,190,flags)||!SetWindowPos(cell[0].Handle,IntPtr.Zero,395,75,325,190,flags))throw new Exception("placement window layout failed: "+Marshal.GetLastWin32Error());
        if(!SetForegroundWindow(MainWindow().Handle))throw new Exception("GECK main window could not be raised");System.Threading.Thread.Sleep(300);Discover();return "{\"arranged\":true,\"windows\":"+TopWindows()+"}";
    }
    static string ObjectPlace(string editorId,out string before) {
        int expectedBefore;if(editorId=="SalvatoreStatic")expectedBefore=0;else if(editorId=="BarracksIntLightKey")expectedBefore=1;else throw new Exception("placement object is not allowlisted");GuardPlugin();GuardDialogs();var view=CellView();var label=CellViewControl(view,"Static",1163);if(Text(label.Handle)!="SalvatoreTestCell Objects")throw new Exception("SalvatoreTestCell is not loaded");var refs=CellViewControl(view,"SysListView32",1156);if(Count(refs)!=expectedBefore)throw new Exception("unexpected SalvatoreTestCell reference count before placement");
        var list=Unique("object list","SysListView32",1041,"FaceClass");int row=FindObjectRow(list,editorId);if(row<0||SelectedRow(list)!=row)throw new Exception("SalvatoreStatic is not the unique selected Object Window row");var render=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="MonitorClass"&&w.Owner==MainWindow().Handle);if(render.Count!=1)throw new Exception("Render Window selector matched "+render.Count+" windows");if(!render[0].Text.StartsWith("SalvatoreTestCell ["))throw new Exception("Render Window has not loaded SalvatoreTestCell: "+render[0].Text);
        RECT item=ListItemRect(list,row),client;if(!GetClientRect(render[0].Handle,out client))throw new Exception("Render Window client bounds unavailable");var from=new POINT{X=item.Left+Math.Max(8,Math.Min(40,(item.Right-item.Left)/3)),Y=(item.Top+item.Bottom)/2};var to=new POINT{X=(client.Left+client.Right)/2,Y=(client.Top+client.Bottom)/2};if(!ClientToScreen(list.Handle,ref from)||!ClientToScreen(render[0].Handle,ref to))throw new Exception("placement coordinates unavailable");before="{\"cell\":\"SalvatoreTestCell\",\"referenceCount\":"+expectedBefore+",\"object\":"+J(editorId)+",\"from\":{\"x\":"+from.X+",\"y\":"+from.Y+"},\"to\":{\"x\":"+to.X+",\"y\":"+to.Y+"}}";
        if(!SetForegroundWindow(list.ActualParent))throw new Exception("Object Window could not be activated");if(!SetCursorPos(from.X,from.Y))throw new Exception("placement cursor start failed");int screenW=GetSystemMetrics(0),screenH=GetSystemMetrics(1);if(screenW<1||screenH<1)throw new Exception("screen metrics unavailable");System.Threading.Thread.Sleep(150);mouse_event(0x0002,0,0,0,UIntPtr.Zero);System.Threading.Thread.Sleep(300);for(int i=1;i<=16;i++){int x=from.X+(to.X-from.X)*i/16,y=from.Y+(to.Y-from.Y)*i/16;uint ax=(uint)Math.Max(0,Math.Min(65535,x*65535/Math.Max(1,screenW-1))),ay=(uint)Math.Max(0,Math.Min(65535,y*65535/Math.Max(1,screenH-1)));mouse_event(0x8001,ax,ay,0,UIntPtr.Zero);System.Threading.Thread.Sleep(50);}System.Threading.Thread.Sleep(250);mouse_event(0x0004,0,0,0,UIntPtr.Zero);
        int expectedAfter=expectedBefore+1;var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();view=CellView();refs=CellViewControl(view,"SysListView32",1156);int count=Count(refs);if(count==expectedAfter)return "{\"cell\":\"SalvatoreTestCell\",\"object\":"+J(editorId)+",\"referenceCount\":"+expectedAfter+",\"placed\":true}";if(count>expectedAfter)throw new Exception("placement created more than one reference");}throw new Exception("placement gesture completed but the reference count did not increment once");
    }
    static string CellContextInspect(out string before) {
        GuardPlugin();GuardDialogs();var cellView=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="ViewerClass"&&w.Text=="Cell View");
        if(cellView.Count!=1)throw new Exception("Cell View selector matched "+cellView.Count+" windows");
        var lists=windows.FindAll(w=>w.ActualParent==cellView[0].Handle&&w.ClassName=="SysListView32"&&w.Id==1155);
        if(lists.Count!=1)throw new Exception("cell list selector matched "+lists.Count+" controls");
        before="{\"cellCount\":"+Count(lists[0])+",\"windows\":"+TopWindows()+"}";
        SetListState(lists[0],-1,0,3);if(!SetForegroundWindow(cellView[0].Handle))throw new Exception("Cell View could not be activated");
        int packed=(30<<16)|30;
        if(!PostMessage(lists[0].Handle,0x0204,(IntPtr)2,(IntPtr)packed)||!PostMessage(lists[0].Handle,0x0205,IntPtr.Zero,(IntPtr)packed))throw new Exception("cell-list right-click post failed");
        System.Threading.Thread.Sleep(1000);Discover();
        var popup=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32768"&&w.Owner==cellView[0].Handle);
        if(popup.Count!=1)throw new Exception("Cell View popup selector matched "+popup.Count+" windows");
        IntPtr menu=(IntPtr)Msg(popup[0].Handle,0x01E1,IntPtr.Zero,IntPtr.Zero);if(menu==IntPtr.Zero)throw new Exception("MN_GETHMENU returned no popup menu");
        var items=new List<string>();MenuWalk(menu,cellView[0].Handle,"cell-popup",items,0);
        return "{\"cellList\":"+WindowJson(lists[0])+",\"popup\":"+WindowJson(popup[0])+",\"items\":["+String.Join(",",items.ToArray())+"]}";
    }
    static string CellNewInspect(out string before) {
        GuardPlugin();GuardDialogs();var cellView=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="ViewerClass"&&w.Text=="Cell View");
        if(cellView.Count!=1)throw new Exception("Cell View selector matched "+cellView.Count+" windows");
        var lists=windows.FindAll(w=>w.ActualParent==cellView[0].Handle&&w.ClassName=="SysListView32"&&w.Id==1155);
        if(lists.Count!=1)throw new Exception("cell list selector matched "+lists.Count+" controls");
        int beforeCount=Count(lists[0]);before="{\"cellCount\":"+beforeCount+",\"editorTitle\":"+J(MainWindow().Text)+",\"windows\":"+TopWindows()+"}";
        var popups=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32768"&&w.Owner==cellView[0].Handle);
        if(popups.Count!=1)throw new Exception("Cell View popup selector matched "+popups.Count+" windows");
        int click=(25<<16)|20;
        if(!PostMessage(popups[0].Handle,0x0201,(IntPtr)1,(IntPtr)click)||!PostMessage(popups[0].Handle,0x0202,IntPtr.Zero,(IntPtr)click))throw new Exception("popup first-item click failed");
        var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();
            var dialogs=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&!IsPreview(w));
            if(dialogs.Count>0)return "{\"dialogs\":"+TopWindows()+",\"inventory\":"+Inspect(500)+"}";
            var rediscovered=windows.Find(w=>w.Handle==lists[0].Handle);
            if(MainWindow().Text.EndsWith("*")||(rediscovered!=null&&Count(rediscovered)!=beforeCount))return "{\"stateChanged\":true,\"editorTitle\":"+J(MainWindow().Text)+",\"inventory\":"+Inspect(500)+"}";
        }throw new Exception("Cell New command dispatched but no identified UI/state change appeared; inspect before retry");
    }
    static string DataOpenInspect(out string before) {
        GuardDialogs();before="{\"editorTitle\":"+J(MainWindow().Text)+",\"windows\":"+TopWindows()+"}";
        PostCommand(MainWindow().Handle,ResourceCommand("MAINMENU","&Data..."),IntPtr.Zero);
        var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<5000){System.Threading.Thread.Sleep(100);Discover();
            var dialogs=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&!IsPreview(w));
            if(dialogs.Count==1)return "{\"dialog\":"+WindowJson(dialogs[0])+",\"inventory\":"+Inspect(500)+"}";
            if(dialogs.Count>1)throw new Exception("Data command produced multiple dialogs");
        }throw new Exception("Data command dispatched but no dialog appeared");
    }
    static WindowInfo DataDialog() {
        var matches=windows.FindAll(w=>w.Parent==IntPtr.Zero&&w.Visible&&w.ClassName=="#32770"&&w.Text=="Data"&&w.Owner==MainWindow().Handle);
        if(matches.Count!=1)throw new Exception("Data dialog selector matched "+matches.Count+" windows");return matches[0];
    }
    static int ListImage(WindowInfo list,int row) {
        IntPtr process=OpenProcess(0x38,false,target);if(process==IntPtr.Zero)throw new Exception("list image process unavailable");
        IntPtr memory=VirtualAllocEx(process,IntPtr.Zero,(UIntPtr)64,0x3000,4);bool safe=true;
        try {if(memory==IntPtr.Zero)throw new Exception("list image allocation failed");byte[] item=new byte[64];
            Array.Copy(BitConverter.GetBytes(2),0,item,0,4);Array.Copy(BitConverter.GetBytes(row),0,item,4,4);UIntPtr n;
            if(!WriteProcessMemory(process,memory,item,(UIntPtr)64,out n))throw new Exception("list image buffer write failed");
            try {if(Msg(list.Handle,0x104B,IntPtr.Zero,memory)==0)throw new Exception("list image query failed");}catch{safe=false;throw;}
            if(!ReadProcessMemory(process,memory,item,(UIntPtr)64,out n))throw new Exception("list image buffer read failed");
            return BitConverter.ToInt32(item,28);
        } finally {if(memory!=IntPtr.Zero&&safe)VirtualFreeEx(process,memory,UIntPtr.Zero,0x8000);CloseHandle(process);}
    }
    static string DataState() {
        var list=DialogControl(DataDialog(),"SysListView32",1056);int count=Count(list);if(count>500)throw new Exception("Data list exceeds limit");
        var rows=new List<string>();for(int i=0;i<count;i++)rows.Add("{\"row\":"+i+",\"file\":"+J(ListCell(list,i))+",\"image\":"+ListImage(list,i)+",\"stateImage\":"+ListState(list,i,0xF000)+"}");
        return "{\"rows\":["+String.Join(",",rows.ToArray())+"]}";
    }
    static void DataToggle(WindowInfo list,int row) {
        int old=ListImage(list,row);if(old!=0&&old!=1)throw new Exception("unsupported Data image index");
        SetListState(list,-1,0,3);SetListState(list,row,3,3);
        Msg(list.Handle,0x1013,(IntPtr)row,(IntPtr)1);
        RECT rect=ListItemRect(list,row);int x=rect.Left+50,y=(rect.Top+rect.Bottom)/2;
        IntPtr point=(IntPtr)((y<<16)|(x&0xffff));
        Msg(list.Handle,0x201,(IntPtr)1,point);Msg(list.Handle,0x202,IntPtr.Zero,point);
        Msg(list.Handle,0x203,(IntPtr)1,point);Msg(list.Handle,0x202,IntPtr.Zero,point);
        var wait=Stopwatch.StartNew();while(wait.ElapsedMilliseconds<2000){if(ListImage(list,row)==1-old)return;System.Threading.Thread.Sleep(50);}
        throw new Exception("Data row toggle did not change actual image state");
    }
    static string DataConfigure(string plugin,out string before) {
        if(plugin!=ExpectedPlugin())throw new Exception("plugin does not match project configuration");
        if(MainWindow().Text.EndsWith("*"))throw new Exception("refusing plugin switch with unsaved changes");
        var dialog=DataDialog();var list=DialogControl(dialog,"SysListView32",1056);int row=FindObjectRow(list,plugin);
        if(row<0)throw new Exception("plugin not found in Data list: "+plugin);
        int master=FindObjectRow(list,"FalloutNV.esm");if(master<0)throw new Exception("FalloutNV.esm not found in Data list");int count=Count(list);if(count>500)throw new Exception("Data list exceeds checkbox safety limit");
        before=DataState();
        for(int i=0;i<count;i++){int expected=(i==master||i==row)?1:0;if(ListImage(list,i)!=expected)DataToggle(list,i);}
        SetListState(list,-1,0,3);SetListState(list,row,3,3);if(SelectedRow(list)!=row)throw new Exception("plugin selection readback failed");
        if(ListColumn(list,row,1)!="Active File"){ButtonCommand(dialog,1121,"Set as Active File");System.Threading.Thread.Sleep(300);Discover();dialog=DataDialog();}
        if(ListColumn(DialogControl(dialog,"SysListView32",1056),row,1)!="Active File")throw new Exception("target plugin is not the active file after selection");
        list=DialogControl(dialog,"SysListView32",1056);
        for(int i=0;i<count;i++)if(ListImage(list,i)!=((i==master||i==row)?1:0))throw new Exception("Data selection changed after setting active file");
        return DataState();
    }
    static string DataLoad(string plugin,out string before) {
        string ignored;before=DataConfigure(plugin,out ignored);
        ButtonCommand(DataDialog(),1,"OK");
        return "{\"plugin\":"+J(plugin)+",\"loadDispatched\":true,\"loaded\":false,\"selection\":"+before+"}";
    }
    static string DataCancel() {
        var dialog=DataDialog();ButtonCommand(dialog,2,"Cancel");WaitClosed(dialog);
        return "{\"cancelled\":true}";
    }
    static string Execute(string[] args,Dictionary<string,string> env,out int code) { requestEnv=env;code=2;targetMode="none";discoveryMode="none";targetMs=0;discoverMs=0;phase=null; var watch=Stopwatch.StartNew(); string operation=args.Length==0?"status":args[0],before=null; try { var allowed=new List<string>{"status","inspect","menus.inspect","menus.resources","filter.set","category.select","objects.find","object.select","object.open","object.cancel","preview.open","preview.close","object.read","object.setModel","object.place","model.inspect","model.browse.inspect","plugin.inspect","plugin.save","world.cells.inspect","world.cells.new.inspect","cell.dialog.cancel","cell.find","cell.show","cell.refs","cell.select","cell.load","cell.context.inspect","cell.new.inspect","window.main.raise","window.layout.place","data.open.inspect","data.load","data.state","data.configure","data.cancel","script.editor.open","script.editor.command","script.editor.inspect","script.compile","script.editor.close","render.steps"};if(!allowed.Contains(operation))throw new Exception("unknown operation");int limit=100;if(operation=="inspect"&&args.Length>1&&(!Int32.TryParse(args[1],out limit)||limit<1||limit>500))throw new Exception("inspect limit must be 1..500");if(operation!="status"&&operation!="inspect"&&operation!="menus.inspect"&&operation!="menus.resources"&&operation!="plugin.inspect"&&operation!="plugin.save"&&operation!="world.cells.inspect"&&operation!="world.cells.new.inspect"&&operation!="cell.dialog.cancel"&&operation!="cell.context.inspect"&&operation!="cell.new.inspect"&&operation!="window.main.raise"&&operation!="window.layout.place"&&operation!="data.open.inspect"&&operation!="script.editor.open"&&operation!="script.editor.inspect"&&operation!="script.editor.close"&&args.Length!=((operation=="object.setModel"||operation=="cell.show"||operation=="render.steps")?3:2))throw new Exception(operation+" requires one argument");phase=Stopwatch.StartNew();targetMode=AcquireTarget()?"cached":"full";targetMs=phase.ElapsedMilliseconds;GuardSession();if(IntPtr.Size!=4)throw new Exception("helper must run as 32-bit");phase=Stopwatch.StartNew();discoveryMode=PrepareWindows(operation);discoverMs=phase.ElapsedMilliseconds;phase=Stopwatch.StartNew();string after;if(Config("MCP","")=="1"&&(operation=="object.place"||operation=="cell.load"||operation=="window.layout.place"))throw new Exception("experimental operation disabled in MCP helper");if(operation=="status")after=Status();else if(operation=="script.editor.open")after=ScriptEditorOpen(out before);else if(operation=="script.editor.command")after=ScriptEditorCommand(args[1],out before);else if(operation=="script.editor.inspect")after=ScriptEditorInspect();else if(operation=="script.compile")after=ScriptCompile(args[1],out before);else if(operation=="script.editor.close")after=ScriptEditorClose(out before);else if(operation=="inspect")after=Inspect(limit);else if(operation=="menus.inspect")after=Menus();else if(operation=="menus.resources")after=ResourceMenus();else if(operation=="world.cells.inspect")after=WorldCellsInspect(out before);else if(operation=="world.cells.new.inspect")after=WorldCellsNewInspect(out before);else if(operation=="cell.dialog.cancel")after=CellDialogCancel(out before);else if(operation=="cell.show")after=CellShow(args[1],args[2],out before);else if(operation=="render.steps")after=RenderSteps(args[1],args[2],out before);else if(operation=="cell.refs")after=CellRefs(args[1],out before);else if(operation=="cell.find")after=CellFind(args[1]);else if(operation=="cell.select")after=CellSelect(args[1],out before);else if(operation=="cell.load")after=CellLoad(args[1],out before);else if(operation=="object.place")after=ObjectPlace(args[1],out before);else if(operation=="cell.context.inspect")after=CellContextInspect(out before);else if(operation=="cell.new.inspect")after=CellNewInspect(out before);else if(operation=="window.main.raise")after=MainRaise();else if(operation=="window.layout.place")after=PlacementLayout();else if(operation=="data.open.inspect")after=DataOpenInspect(out before);else if(operation=="data.configure")after=DataConfigure(args[1],out before);else if(operation=="data.cancel")after=DataCancel();else if(operation=="data.state")after=DataState();else if(operation=="data.load")after=DataLoad(args[1],out before);else if(operation=="filter.set")after=FilterSet(args[1],out before);else if(operation=="category.select")after=CategorySelect(args[1],out before);else if(operation=="objects.find")after=ObjectsFind(args[1]);else if(operation=="plugin.inspect")after=PluginInspect();else if(operation=="plugin.save")after=PluginSave(args.Length==2?args[1]:"",out before);else if(operation=="model.browse.inspect")after=ModelBrowse(args[1],out before);else if(operation=="model.inspect")after=ModelInspect(args[1],out before);else if(operation=="object.read")after=ObjectRead(args[1],out before);else if(operation=="object.setModel")after=ObjectSetModel(args[1],args[2],out before);else if(operation=="preview.close")after=PreviewClose(args[1],out before);else if(operation=="object.cancel")after=ObjectCancel(args[1],out before);else if(operation=="preview.open")after=PreviewOpen(args[1],out before);else if(operation=="object.open")after=ObjectOpen(args[1],out before);else after=ObjectSelect(args[1],out before);code=0;FinishWindows(operation,true);return Result(true,operation,before,after,watch.ElapsedMilliseconds,null)+"";}catch(Exception ex){code=2;FinishWindows(operation,false);string windowsJson;try{windowsJson=TopWindows();}catch{windowsJson="[]";}return Result(false,operation,before,"{\"windows\":"+windowsJson+"}",watch.ElapsedMilliseconds,ex.Message);}
        finally{requestEnv=null;} }

    // ---- Persistent worker (M1) -------------------------------------------------
    // One long-lived helper per MCP server. Requests are one JSON object per line on
    // stdin; each response is one JSON line on stdout. The GECK process, command IDs
    // and window inventory are cached, with cheap validation before each reuse.
    static bool serveMode;
    static string targetMode="none",discoveryMode="none";
    static long targetMs,discoverMs;
    static Stopwatch phase;
    static uint cachedPid;static long cachedTicks;static Stopwatch sinceTargetCheck;
    static string windowFingerprint;static uint windowCachePid;static bool windowCacheUsable;
    static int cacheHits,cacheMisses,served;
    // Operations that neither create nor destroy windows, and read child text live.
    static readonly List<string> CacheSafe=new List<string>{"status","filter.set","category.select","objects.find","object.select","cell.find","data.state","plugin.inspect","menus.resources"};
    // Process.MainModule is slow under Wine (~100 ms); the path cannot change for a live PID.
    static uint exePid;static string exePath;
    static string GeckExecutable() {if(exePath==null||exePid!=target){exePath=Process.GetProcessById((int)target).MainModule.FileName;exePid=target;}return exePath;}
    static bool AcquireTarget() {
        if(serveMode&&cachedPid!=0&&sinceTargetCheck!=null&&sinceTargetCheck.ElapsedMilliseconds<5000) {
            try{var p=Process.GetProcessById((int)cachedPid);if(!p.HasExited&&p.StartTime.ToUniversalTime().Ticks==cachedTicks){target=cachedPid;return true;}}catch{}
        }
        var candidates=Process.GetProcessesByName("GECK");
        if(candidates.Length!=1){cachedPid=0;windowCacheUsable=false;throw new Exception("expected exactly one GECK process; found "+candidates.Length);}
        uint pid=(uint)candidates[0].Id;long ticks=candidates[0].StartTime.ToUniversalTime().Ticks;
        if(pid!=cachedPid||ticks!=cachedTicks){windowCacheUsable=false;resourceCache.Clear();exePath=null;}
        target=pid;cachedPid=pid;cachedTicks=ticks;sinceTargetCheck=Stopwatch.StartNew();return false;
    }
    static string TopFingerprint() {
        var b=new StringBuilder();
        EnumWindows(delegate(IntPtr top,IntPtr unused){uint pid;GetWindowThreadProcessId(top,out pid);if(pid!=target)return true;string text;try{text=Text(top);}catch{text="<unavailable>";}
            b.Append(top.ToInt64()).Append('|').Append(IsWindowVisible(top)?1:0).Append(IsWindowEnabled(top)?1:0).Append('|').Append(Class(top)).Append('|').Append(text).Append('\n');return true;},IntPtr.Zero);
        return b.ToString();
    }
    static string PrepareWindows(string operation) {
        if(serveMode&&windowCacheUsable&&windowCachePid==target&&CacheSafe.Contains(operation)) {
            string fingerprint=TopFingerprint();bool alive=fingerprint==windowFingerprint;
            if(alive)foreach(var w in windows)if(!IsWindow(w.Handle)){alive=false;break;}
            if(alive){cacheHits++;return "cached";}
        }
        cacheMisses++;Discover();
        if(serveMode){windowFingerprint=TopFingerprint();windowCachePid=target;windowCacheUsable=true;}
        return "full";
    }
    static void FinishWindows(string operation,bool ok) {if(!ok||!CacheSafe.Contains(operation))windowCacheUsable=false;}
    static string WorkerJson(long total) {
        return "{\"mode\":"+J(serveMode?"persistent":"oneshot")+",\"target\":"+J(targetMode)+",\"discovery\":"+J(discoveryMode)+",\"targetMs\":"+targetMs+",\"discoverMs\":"+discoverMs+",\"operationMs\":"+(phase==null?0:phase.ElapsedMilliseconds)+",\"served\":"+served+",\"cacheHits\":"+cacheHits+",\"cacheMisses\":"+cacheMisses+"}";
    }
    static string WithFields(string json,string id,string extra) {
        // json is a Result object: insert id first and extra fields last.
        string head=id==null?"{":"{\"id\":"+id+",";
        return head+json.Substring(1,json.Length-2)+(extra==null?"":","+extra)+"}";
    }
    // Minimal JSON reader for the request shape: objects, arrays, strings, numbers, literals.
    class JsonReader {
        readonly string s;int i;
        public JsonReader(string text){s=text;}
        public static object Parse(string text){var r=new JsonReader(text);object v=r.Value();r.Ws();if(r.i!=r.s.Length)throw new Exception("trailing JSON content");return v;}
        void Ws(){while(i<s.Length&&(s[i]==' '||s[i]=='\t'||s[i]=='\r'||s[i]=='\n'))i++;}
        char Peek(){Ws();if(i>=s.Length)throw new Exception("unexpected end of JSON");return s[i];}
        object Value(){
            char c=Peek();
            if(c=='{'){i++;var o=new Dictionary<string,object>();if(Peek()=='}'){i++;return o;}
                while(true){if(Peek()!='"')throw new Exception("expected JSON key");string k=Str();if(Peek()!=':')throw new Exception("expected ':'");i++;o[k]=Value();c=Peek();i++;if(c=='}')return o;if(c!=',')throw new Exception("expected ',' or '}'");}}
            if(c=='['){i++;var a=new List<object>();if(Peek()==']'){i++;return a;}
                while(true){a.Add(Value());c=Peek();i++;if(c==']')return a;if(c!=',')throw new Exception("expected ',' or ']'");}}
            if(c=='"')return Str();
            int start=i;while(i<s.Length&&"+-0123456789.eEtruefalsn".IndexOf(s[i])>=0)i++;
            string lit=s.Substring(start,i-start);if(lit=="true")return true;if(lit=="false")return false;if(lit=="null")return null;
            double d;if(lit.Length==0||!Double.TryParse(lit,System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out d))throw new Exception("invalid JSON value");return lit;
        }
        string Str(){
            i++;var b=new StringBuilder();
            while(true){if(i>=s.Length)throw new Exception("unterminated JSON string");char c=s[i++];if(c=='"')return b.ToString();
                if(c!='\\'){b.Append(c);continue;}if(i>=s.Length)throw new Exception("bad JSON escape");char e=s[i++];
                if(e=='u'){if(i+4>s.Length)throw new Exception("bad unicode escape");b.Append((char)Convert.ToInt32(s.Substring(i,4),16));i+=4;}
                else if(e=='n')b.Append('\n');else if(e=='r')b.Append('\r');else if(e=='t')b.Append('\t');else if(e=='b')b.Append('\b');else if(e=='f')b.Append('\f');else b.Append(e);}
        }
    }
    static string IdJson(object id) {if(id==null)return "null";if(id is string){string t=(string)id;double d;if(Double.TryParse(t,System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out d)&&t.Length<20&&t.IndexOf('"')<0)return t;return J(t);}return J(id.ToString());}
    static Dictionary<string,string> RequestEnv(Dictionary<string,object> request) {
        var env=new Dictionary<string,string>();object raw;
        if(request.TryGetValue("env",out raw)&&raw!=null){var map=raw as Dictionary<string,object>;if(map==null)throw new Exception("env must be an object");
            foreach(var pair in map){if(!pair.Key.StartsWith("GECK_BRIDGE_"))throw new Exception("env key outside GECK_BRIDGE_ namespace");if(pair.Value!=null&&!(pair.Value is string))throw new Exception("env values must be strings");env[pair.Key]=(string)pair.Value;}}
        return env;
    }
    static string[] RequestArgs(object raw) {
        var list=raw as List<object>;if(list==null||list.Count==0||list.Count>8)throw new Exception("args must be a non-empty array of at most 8 strings");
        var args=new string[list.Count];for(int k=0;k<list.Count;k++){if(!(list[k] is string))throw new Exception("args must be strings");args[k]=(string)list[k];}return args;
    }
    static string HandleRequest(string line,out bool stop) {
        stop=false;var watch=Stopwatch.StartNew();string id="null";
        try {
            var request=JsonReader.Parse(line) as Dictionary<string,object>;if(request==null)throw new Exception("request must be a JSON object");
            object rawId;if(request.TryGetValue("id",out rawId))id=IdJson(rawId);
            var env=RequestEnv(request);object raw;
            if(request.TryGetValue("batch",out raw)) {
                var steps=raw as List<object>;if(steps==null||steps.Count==0||steps.Count>16)throw new Exception("batch must contain 1..16 steps");
                bool stopOnError=true;object soe;if(request.TryGetValue("stopOnError",out soe)&&soe is bool)stopOnError=(bool)soe;
                var results=new List<string>();bool allOk=true;
                foreach(object step in steps){var map=step as Dictionary<string,object>;object stepArgs;if(map==null||!map.TryGetValue("args",out stepArgs))throw new Exception("batch step requires args");
                    var a=RequestArgs(stepArgs);if(a[0]=="serve"||a[0]=="shutdown"||a[0]=="ping")throw new Exception("control operations cannot be batched");
                    int code;string r=Execute(a,env,out code);served++;results.Add(r);if(code!=0){allOk=false;if(stopOnError)break;}}
                return "{\"id\":"+id+",\"ok\":"+allOk.ToString().ToLower()+",\"operation\":\"batch\",\"target\":\"GECK\",\"before\":null,\"after\":{\"steps\":"+steps.Count+",\"completed\":"+results.Count+"},\"results\":["+String.Join(",",results.ToArray())+"],\"elapsedMs\":"+watch.ElapsedMilliseconds+",\"error\":"+(allOk?"null":J("batch step failed"))+"}";
            }
            object argsRaw;if(!request.TryGetValue("args",out argsRaw))throw new Exception("request requires args");
            var args=RequestArgs(argsRaw);
            if(args[0]=="ping")return "{\"id\":"+id+",\"ok\":true,\"operation\":\"ping\",\"target\":\"worker\",\"before\":null,\"after\":{\"protocol\":1,\"served\":"+served+",\"cachedPid\":"+cachedPid+",\"windowCache\":"+windowCacheUsable.ToString().ToLower()+",\"cacheHits\":"+cacheHits+",\"cacheMisses\":"+cacheMisses+"},\"elapsedMs\":"+watch.ElapsedMilliseconds+",\"error\":null}";
            if(args[0]=="invalidate"){windowCacheUsable=false;cachedPid=0;resourceCache.Clear();return "{\"id\":"+id+",\"ok\":true,\"operation\":\"invalidate\",\"target\":\"worker\",\"before\":null,\"after\":{\"invalidated\":true},\"elapsedMs\":0,\"error\":null}";}
            if(args[0]=="shutdown"){stop=true;return "{\"id\":"+id+",\"ok\":true,\"operation\":\"shutdown\",\"target\":\"worker\",\"before\":null,\"after\":{\"served\":"+served+"},\"elapsedMs\":0,\"error\":null}";}
            if(args[0]=="serve")throw new Exception("serve cannot be nested");
            int exit;string result=Execute(args,env,out exit);served++;
            return WithFields(result,id,null);
        } catch(Exception ex) {
            return "{\"id\":"+id+",\"ok\":false,\"operation\":\"protocol\",\"target\":\"worker\",\"before\":null,\"after\":null,\"elapsedMs\":"+watch.ElapsedMilliseconds+",\"error\":"+J("PROTOCOL_ERROR: "+ex.Message)+"}";
        }
    }
    static int Serve(string[] args) {
        serveMode=true;
        // Optional file endpoints allow testing without a shell (CrossOver Run Command):
        // serve --input requests.jsonl --output responses.jsonl
        string inPath=Environment.GetEnvironmentVariable("GECK_BRIDGE_SERVE_INPUT"),outPath=Environment.GetEnvironmentVariable("GECK_BRIDGE_OUTPUT");
        for(int k=1;k+1<args.Length;k+=2){if(args[k]=="--input")inPath=args[k+1];else if(args[k]=="--output")outPath=args[k+1];else throw new Exception("unknown serve option: "+args[k]);}
        System.IO.TextReader input=String.IsNullOrEmpty(inPath)?Console.In:new System.IO.StreamReader(inPath);
        System.IO.TextWriter output=String.IsNullOrEmpty(outPath)?Console.Out:new System.IO.StreamWriter(outPath,false,new UTF8Encoding(false));
        output.WriteLine("{\"id\":null,\"ok\":true,\"operation\":\"hello\",\"target\":\"worker\",\"before\":null,\"after\":{\"protocol\":1,\"workerPid\":"+Process.GetCurrentProcess().Id+",\"pointerBytes\":"+IntPtr.Size+"},\"elapsedMs\":0,\"error\":null}");output.Flush();
        string line;
        while((line=input.ReadLine())!=null) {
            line=line.Trim();if(line.Length==0)continue;bool stop;
            output.WriteLine(HandleRequest(line,out stop));output.Flush();
            if(stop)break;
        }
        output.Flush();if(output!=Console.Out)output.Close();
        return 0;
    }
    static int Main(string[] args) {
        if(args.Length>0&&args[0]=="serve")return Serve(args);
        int code;string result=Execute(args,null,out code);Console.WriteLine(result);
        string outPath=Environment.GetEnvironmentVariable("GECK_BRIDGE_OUTPUT");
        if(!String.IsNullOrEmpty(outPath))System.IO.File.WriteAllText(outPath,result+"\n",new UTF8Encoding(false));
        return code;
    }

}

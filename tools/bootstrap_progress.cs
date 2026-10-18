// Embedded into the generated PowerShell bootstrap by build_installer.py.
using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
namespace DevSiftTerminalV2 {
public sealed class Display : IDisposable {
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int n);
    [DllImport("kernel32.dll")] static extern bool GetConsoleMode(IntPtr h, out uint mode);
    [DllImport("kernel32.dll")] static extern bool SetConsoleMode(IntPtr h, uint mode);
    readonly object gate = new object();
    readonly Stopwatch clock = Stopwatch.StartNew();
    readonly string operation;
    Timer timer;
    IntPtr handle;
    uint oldMode;
    bool interactive, active, closed;
    int percent, tick, stages;
    long received = -1, total;
    string stage = "Checking Python 3.12+", lastStage;
    public Display(string action) {
        operation = action;
        handle = GetStdHandle(-12);
        interactive = !Console.IsErrorRedirected && GetConsoleMode(handle, out oldMode);
        if (interactive) interactive = SetConsoleMode(handle, oldMode | 4);
        if (interactive) timer = new Timer(_ => { lock(gate) { if(!closed) Draw(); } }, null, 200, 200);
    }
    static string Clip(string text, int limit) {
        var b = new StringBuilder(); int used = 0;
        for(int i=0; i<text.Length; i++) {
            int cp = char.ConvertToUtf32(text,i);
            var cat = CharUnicodeInfo.GetUnicodeCategory(text,i);
            string s = char.ConvertFromUtf32(cp);
            if(cp>65535) i++;
            int width = 1;
            if(cat==UnicodeCategory.Control || cat==UnicodeCategory.Format || cat==UnicodeCategory.Surrogate) s=" ";
            else if(cat==UnicodeCategory.NonSpacingMark || cat==UnicodeCategory.EnclosingMark || cat==UnicodeCategory.SpacingCombiningMark) width=0;
            else if(cp>=0x1100 && (cp<=0x115f || cp==0x2329 || cp==0x232a ||
                (cp>=0x2e80 && cp<=0xa4cf) || (cp>=0xac00 && cp<=0xd7a3) ||
                (cp>=0xf900 && cp<=0xfaff) || (cp>=0xfe10 && cp<=0xfe6f) ||
                (cp>=0xff01 && cp<=0xff60) || (cp>=0xffe0 && cp<=0xffe6) ||
                cp>=0x1f000)) width=2;
            if(used+width>limit) break;
            b.Append(s); used+=width;
        }
        return b.ToString();
    }
    void Draw() {
        if(closed) return;
        if(!interactive) {
            if(stage!=lastStage && stages<24) {
                Console.Error.WriteLine("DevSift "+operation+": "+Clip(stage,160));
                lastStage=stage; stages++;
            }
            return;
        }
        int width;
        try { width=Math.Max(1,Console.WindowWidth-1); } catch { width=79; }
        int p=received<0 ? percent : total>0 ? (int)Math.Min(100,100.0*received/total) : -1;
        string label=received<0 ? "Overall setup" : "Downloading";
        string suffix=p>=0 ? " "+p+"%" : " size unknown";
        int size=Math.Min(32,Math.Max(1,width-label.Length-suffix.Length-3));
        int filled=p>=0 ? p*size/100 : tick%size;
        string bar=p>=0 ? new string('#',filled)+new string('-',size-filled) :
            new string('-',filled)+"#"+new string('-',size-filled-1);
        string top=label+" ["+bar+"]"+suffix;
        string detail=received<0 ? "" : total>0 ? received+"/"+total+"B " : received+"B received ";
        string bottom="|/-\\"[tick++%4]+" devsift "+operation+": "+detail+stage+" ("+clock.Elapsed.TotalSeconds.ToString("F1",CultureInfo.InvariantCulture)+"s)";
        if(!active) { Console.Error.Write("\x1b[?25l\r\n"); active=true; }
        Console.Error.Write("\r\x1b[1A\x1b[2K"+Clip(top,width)+"\r\n\x1b[2K"+Clip(bottom,width)+"\r");
        Console.Error.Flush();
    }
    public void Update(int value,string text) {
        lock(gate) {
            if(closed) return;
            if(stage!=text) clock.Restart();
            percent=Math.Max(0,Math.Min(100,value)); stage=text; received=-1;
            Draw();
        }
    }
    public void Transfer(long count,long length,string text) {
        lock(gate) { if(closed) return; received=count; total=length; stage=text; Draw(); }
    }
    public void Dispose() {
        lock(gate) {
            if(closed) return;
            closed=true;
            if(timer!=null) timer.Dispose();
            if(active) {
                Console.Error.Write("\r\x1b[2K\x1b[1A\r\x1b[2K\x1b[?25h");
                Console.Error.Flush(); active=false;
            }
            if(interactive) SetConsoleMode(handle,oldMode);
        }
    }
}
}

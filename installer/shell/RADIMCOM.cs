// RADIMCOM.exe: the Windows app around the RADIMCOM server.
//
// Starts the server (python app.py, without a console window) unless one already answers on its port, shows the page
// in its own window (WebView2, the Edge engine that comes with Windows) with the RADIMCOM icon on the taskbar, and
// keeps a tray icon. Closing the window leaves the server running in the tray (decoders, recordings go on);
// "Exit" in the tray menu stops it. All processes of the server are in a job object: they end with this program.
//
//   RADIMCOM.exe            start (a second start only brings the window up)
//   RADIMCOM.exe --tray     start into the tray (autostart with Windows)
//
// Built by installer/make_installer.py with csc.exe of the .NET Framework 4.x (C# 5: no $"", ?., =>).
// Python: python\python.exe (installed), .venv\Scripts\python.exe (development copy), else python from PATH.
// The server ends gracefully when its stdin closes (launcher.py / app.py with RADIMCOM_SHELL set).

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: System.Reflection.AssemblyTitle("RADIMCOM")]
[assembly: System.Reflection.AssemblyProduct("RADIMCOM")]
[assembly: System.Reflection.AssemblyDescription("RADIMCOM SDR receiver")]

namespace Radimcom
{
    static class Program
    {
        public static string Base;
        public static string Id;

        [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr value);
        [DllImport("user32.dll")] static extern bool SetProcessDPIAware();

        [STAThread]
        static int Main(string[] args)
        {
            Base = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
            string id = FolderId(Base);
            Id = id;
            bool tray = Array.IndexOf(args, "--tray") >= 0;
            Shell.StartFullArg = Array.IndexOf(args, "--fullscreen") >= 0;
            Shell.StartSetupArg = Array.IndexOf(args, "--setup") >= 0;
            bool created;
            if (Array.IndexOf(args, "--exit") >= 0)
            {
                // the uninstaller: a running RADIMCOM stops its server and ends; wait for it (up to 30 s)
                try
                {
                    var running = Mutex.OpenExisting("RADIMCOM-shell-" + id);
                    EventWaitHandle.OpenExisting("RADIMCOM-exit-" + id).Set();
                    try { running.WaitOne(30000); } catch (AbandonedMutexException) { }
                }
                catch (Exception) { }
                return 0;
            }
            // the setup looks for "RADIMCOM-app-<folder>" (radimcom.iss AppMutexName: running here, close it first)
            var anyMutex = new Mutex(false, "RADIMCOM-app-" + Base.ToLowerInvariant().Replace('\\', '_').Replace(':', '_'));
            var mutex = new Mutex(true, "RADIMCOM-shell-" + id, out created);
            if (!created)
            {
                // already running: bring its window up, or (--setup) let it switch to the SDR setup
                try { EventWaitHandle.OpenExisting((Shell.StartSetupArg ? "RADIMCOM-setup-" : "RADIMCOM-show-") + id).Set(); }
                catch (Exception) { }
                return 0;
            }
            try { SetProcessDpiAwarenessContext(new IntPtr(-4)); }     // per monitor v2 (Windows 10 1703+)
            catch (Exception) { try { SetProcessDPIAware(); } catch (Exception) { } }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            var show = new EventWaitHandle(false, EventResetMode.AutoReset, "RADIMCOM-show-" + id);
            var exit = new EventWaitHandle(false, EventResetMode.AutoReset, "RADIMCOM-exit-" + id);
            var shell = new Shell(show, exit, tray);
            Application.Run(shell);
            GC.KeepAlive(mutex);
            GC.KeepAlive(anyMutex);
            return 0;
        }

        static string FolderId(string path)
        {
            uint h = 2166136261;
            foreach (char c in path.ToLowerInvariant()) { h ^= c; h *= 16777619; }
            return h.ToString("x8");
        }

        public static string Data(string name) { return Path.Combine(Path.Combine(Base, "data"), name); }
    }

    /// <summary>The server process (python app.py) inside a kill-on-close job object.</summary>
    class Server
    {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr a, string name);
        [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int cls, ref JobExtended info, int size);
        [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll")] static extern bool TerminateJobObject(IntPtr job, uint code);

        [StructLayout(LayoutKind.Sequential)]
        struct JobBasic
        {
            public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass, SchedulingClass;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct IoCounters { public ulong a, b, c, d, e, f; }
        [StructLayout(LayoutKind.Sequential)]
        struct JobExtended
        {
            public JobBasic Basic;
            public IoCounters Io;
            public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
        }

        readonly IntPtr job;
        Process proc;
        StreamWriter console;
        readonly object consoleLock = new object();
        readonly LinkedList<string> tail = new LinkedList<string>();
        public event Action<int> Exited;
        public bool Stopping;

        public Server()
        {
            job = CreateJobObject(IntPtr.Zero, null);
            var info = new JobExtended();
            info.Basic.LimitFlags = 0x2000 | 0x0800;     // KILL_ON_JOB_CLOSE | BREAKAWAY_OK (programs it starts may leave the job)
            SetInformationJobObject(job, 9, ref info, Marshal.SizeOf(typeof(JobExtended)));
        }

        public bool Running { get { return proc != null && !proc.HasExited; } }

        public static string Python()
        {
            foreach (var p in new[] { @"python\python.exe", @".venv\Scripts\python.exe" })
            {
                string f = Path.Combine(Program.Base, p);
                if (File.Exists(f)) return f;
            }
            return "python.exe";
        }

        public void Start() { Start("app.py", "console.log"); }

        /// <summary>python -u script (app.py: the receiver, setup_web.py --port n: the SDR setup).</summary>
        public void Start(string script, string logName)
        {
            Stopping = false;
            lock (tail) tail.Clear();
            string logs = Program.Data("server_logs");
            Directory.CreateDirectory(logs);
            lock (consoleLock)
            {
                // what the server prints before it opens its own log (or when it cannot start at all)
                console = new StreamWriter(Path.Combine(logs, logName), false, new UTF8Encoding(false));
                console.AutoFlush = true;
            }
            var psi = new ProcessStartInfo(Python(), "-u " + script);
            psi.WorkingDirectory = Program.Base;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardInput = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.StandardOutputEncoding = Encoding.UTF8;
            psi.StandardErrorEncoding = Encoding.UTF8;
            psi.EnvironmentVariables["RADIMCOM_SHELL"] = Process.GetCurrentProcess().Id.ToString();
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            psi.EnvironmentVariables.Remove("PYTHONHOME");
            psi.EnvironmentVariables.Remove("PYTHONPATH");
            var p = new Process();
            p.StartInfo = psi;
            p.EnableRaisingEvents = true;
            p.OutputDataReceived += (s, e) => Line(e.Data);
            p.ErrorDataReceived += (s, e) => Line(e.Data);
            p.Exited += (s, e) =>
            {
                int code = -1;
                try { code = p.ExitCode; } catch (Exception) { }
                Line("[server ended, exit code " + code + "]");
                if (Exited != null) Exited(code);
            };
            Line("RADIMCOM: " + psi.FileName + " " + script + " in " + Program.Base);
            p.Start();
            AssignProcessToJobObject(job, p.Handle);
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            proc = p;
        }

        void Line(string s)
        {
            if (s == null) return;
            lock (consoleLock) { if (console != null) try { console.WriteLine(s); } catch (Exception) { } }
            lock (tail) { tail.AddLast(s); while (tail.Count > 40) tail.RemoveFirst(); }
        }

        public string Tail()
        {
            lock (tail) return string.Join("\n", tail);
        }

        /// <summary>Graceful stop (stdin closes: the VFO receivers end, then the launcher), after the timeout the whole job.</summary>
        public void Stop(int timeoutMs)
        {
            Stopping = true;
            var p = proc;
            if (p != null && !p.HasExited)
            {
                try { p.StandardInput.Close(); } catch (Exception) { }
                if (!p.WaitForExit(timeoutMs)) TerminateJobObject(job, 1);
                else Thread.Sleep(300);
            }
            TerminateJobObject(job, 1);       // anything left (decoders started from lib\)
        }
    }

    class Shell : Form
    {
        readonly EventWaitHandle showEvent;
        readonly NotifyIcon tray;
        readonly Server server = new Server();
        WebView2 web;
        bool webOk;
        bool ownServer;
        bool exiting;
        bool trayHintShown;
        bool startHidden;
        bool ready;                  // the server answers: the page can be shown
        string status = "";          // the status page shown until then
        int port = 8434;
        string Url { get { return "http://localhost:" + port + "/"; } }
        FormWindowState lastState = FormWindowState.Normal;
        Rectangle lastBounds;

        public Shell(EventWaitHandle show, EventWaitHandle exit, bool hidden)
        {
            var te = new Thread(() => { exit.WaitOne(); BeginInvokeSafe(ExitAll); });
            te.IsBackground = true;
            te.Start();
            showEvent = show;
            startHidden = hidden;
            Text = "RADIMCOM";
            Icon = AppIcon(32);
            BackColor = Color.FromArgb(10, 20, 34);
            MinimumSize = new Size(640, 120);       // low: the head alone (lower part hidden) is wide and low
            StartPosition = FormStartPosition.Manual;
            LoadPlacement();

            tray = new NotifyIcon();
            tray.Icon = Icon;
            tray.Text = "RADIMCOM";
            var menu = new ContextMenuStrip();
            var open = menu.Items.Add("Open RADIMCOM", null, (s, e) => ShowWindow());
            open.Font = new Font(open.Font, FontStyle.Bold);
            menu.Items.Add("Open in the web browser", null, (s, e) => OpenUrl(Url));
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Data folder", null, (s, e) => OpenPath(Path.Combine(Program.Base, "data")));
            menu.Items.Add("Server log", null, (s, e) => OpenLog());
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("SDR setup…", null, (s, e) => EnterSetup());
            var miStart = menu.Items.Add("Start server", null, (s, e) => StartServer());
            var miStop = menu.Items.Add("Stop server", null, (s, e) => StopServer());
            var miRestart = menu.Items.Add("Restart server", null, (s, e) => RestartServer());
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Exit RADIMCOM", null, (s, e) => ExitAll());
            menu.Opening += (s, e) =>
            {
                // our server running / stopped; a server started elsewhere (start.bat) is not ours to start or stop
                bool running = ownServer && server.Running;
                bool external = !ownServer && ready;
                miStart.Enabled = !running && !external && !setupMode && !busy;
                miStop.Enabled = running && !setupMode && !busy;
                miRestart.Enabled = (running || setupMode) && !busy;
            };
            tray.ContextMenuStrip = menu;
            tray.MouseClick += (s, e) => { if (e.Button == MouseButtons.Left) ShowWindow(); };
            tray.Visible = true;

            server.Exited += code => BeginInvokeSafe(() => ServerExited(code));
            setupServer.Exited += code => BeginInvokeSafe(() => SetupExited(code));
            var setupEvent = new EventWaitHandle(false, EventResetMode.AutoReset, "RADIMCOM-setup-" + Program.Id);
            var ts = new Thread(() =>
            {
                while (true)
                {
                    setupEvent.WaitOne();
                    BeginInvokeSafe(EnterSetup);
                }
            });
            ts.IsBackground = true;
            ts.Start();
            var t = new Thread(() =>
            {
                while (true)
                {
                    showEvent.WaitOne();
                    BeginInvokeSafe(ShowWindow);
                }
            });
            t.IsBackground = true;
            t.Start();
        }

        protected override void SetVisibleCore(bool value)
        {
            if (startHidden)
            {
                if (!IsHandleCreated) CreateHandle();       // --tray: the server starts, the window stays hidden
                value = false;
            }
            base.SetVisibleCore(value);
        }

        void BeginInvokeSafe(Action a)
        {
            try { if (IsHandleCreated && !IsDisposed) BeginInvoke(a); } catch (Exception) { }
        }

        bool initDone;
        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            SetWindowIcons();          // also after the handle is recreated (full screen changes the border style)
            if (initDone) return;
            initDone = true;
            ReadPort();
            web = new WebView2();
            web.Dock = DockStyle.Fill;
            web.DefaultBackgroundColor = BackColor;
            Controls.Add(web);
            BeginInvoke(new Action(async () =>
            {
                var w = InitWeb();         // finishes only when the window is shown (the control needs its handle)
                if (StartSetupArg) EnterSetup();
                else await StartOrAttach();
                await w;
            }));
        }

        async Task InitWeb()
        {
            try
            {
                var opt = new CoreWebView2EnvironmentOptions("--autoplay-policy=no-user-gesture-required");
                var env = await CoreWebView2Environment.CreateAsync(null, Program.Data("webview2"), opt);
                await web.EnsureCoreWebView2Async(env);
                SetupWeb(web.CoreWebView2);
                webOk = true;
                Home();
            }
            catch (Exception ex)
            {
                // no WebView2 runtime (very old Windows 10 without updates): the page opens in the browser instead
                webOk = false;
                Controls.Remove(web);
                var l = new Label();
                l.Dock = DockStyle.Fill;
                l.ForeColor = Color.White;
                l.TextAlign = ContentAlignment.MiddleCenter;
                l.Text = "The WebView2 runtime is missing (" + ex.Message + ").\nRADIMCOM opens in the web browser; "
                         + "the server runs in the tray.\nInstall WebView2: https://go.microsoft.com/fwlink/p/?LinkId=2124703";
                Controls.Add(l);
                if (ready) OpenUrl(Url);
            }
        }

        /// <summary>The page when the server is ready, else the last status page.</summary>
        void Home()
        {
            if (!webOk || web.CoreWebView2 == null) return;
            if (setupMode && setupReady) web.CoreWebView2.Navigate(SetupUrl);
            else if (!setupMode && ready) web.CoreWebView2.Navigate(Url);
            else web.CoreWebView2.NavigateToString(status);
        }

        // ---- SDR setup in the window (setup_web.py): the receiver stops, the wizard runs, then the receiver starts again
        public static bool StartSetupArg;     // RADIMCOM.exe --setup (Start menu, end of the installation)
        const int SetupPort = 8433;
        readonly Server setupServer = new Server();
        bool setupMode, setupReady;
        string SetupUrl { get { return "http://localhost:" + SetupPort + "/"; } }

        async void EnterSetup()
        {
            if (exiting) return;
            if (setupMode) { ShowWindow(); return; }
            int p = port;
            if (!ownServer && (ready || await Task.Run(() => Answers(p, 800))))
            {
                ShowWindow();
                MessageBox.Show(this, "The receiver was started elsewhere (start.bat?). Close it first: the SDR setup needs the dongles.",
                                "RADIMCOM SDR setup", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            setupMode = true;
            setupReady = false;
            ready = false;
            ShowWindow();
            if (server.Running)
            {
                Page(Html("SDR setup", "Stopping the receiver (the dongles must be free)…", true));
                await Task.Run(() => server.Stop(20000));
            }
            Page(Html("SDR setup", "Looking for the SDR dongles…", true));
            try { setupServer.Start("setup_web.py --port " + SetupPort, "console_setup.log"); }
            catch (Exception ex)
            {
                Page(Html("The SDR setup could not start", "Python: " + Server.Python() + "\n" + ex.Message, false));
                return;
            }
            var sw = Stopwatch.StartNew();
            while (setupServer.Running && setupMode)
            {
                if (await Task.Run(() => Answers(SetupPort, 1000))) break;
                if (sw.Elapsed.TotalSeconds > 60)
                {
                    Page(Html("The SDR setup does not answer", setupServer.Tail(), false));
                    return;
                }
                await Task.Delay(300);
            }
            if (!setupServer.Running || !setupMode) return;
            setupReady = true;
            tray.Text = "RADIMCOM: SDR setup";
            Home();
        }

        /// <summary>The wizard saved (or was cancelled / closed): it ends and the receiver starts with the new vfos.json.</summary>
        async void LeaveSetup()
        {
            if (!setupMode) return;
            setupMode = false;
            setupReady = false;
            Page(Html("Starting RADIMCOM…", "The receivers open their SDR dongles.", true));
            await Task.Run(() => setupServer.Stop(3000));
            if (exiting) return;
            ReadPort();
            await StartOrAttach();
        }

        void SetupExited(int code)
        {
            if (!setupMode || setupServer.Stopping || exiting) return;
            setupReady = false;
            Page(Html("The SDR setup has ended", "Exit code " + code + ":\n\n" + setupServer.Tail(), false));
            ShowWindow();
        }

        void SetupWeb(CoreWebView2 cw)
        {
            cw.Settings.IsStatusBarEnabled = false;
            cw.DocumentTitleChanged += (s, e) =>
            {
                string t = cw.DocumentTitle;
                Text = string.IsNullOrEmpty(t) || t.StartsWith("localhost") ? "RADIMCOM" : t;
            };
            // links to other sites (release page, QRZ, maps …) go to the normal browser
            cw.NewWindowRequested += (s, e) =>
            {
                if (!IsLocal(e.Uri)) { e.Handled = true; OpenUrl(e.Uri); }
            };
            cw.NavigationStarting += (s, e) =>
            {
                if (!IsLocal(e.Uri) && !e.Uri.StartsWith("data:") && !e.Uri.StartsWith("about:")) { e.Cancel = true; OpenUrl(e.Uri); }
            };
            // the page is our own: microphone (TX audio), clipboard, notifications without asking
            cw.PermissionRequested += (s, e) => { if (IsLocal(e.Uri)) e.State = CoreWebView2PermissionState.Allow; };
            cw.ContainsFullScreenElementChanged += (s, e) => SetFullScreen(cw.ContainsFullScreenElement);
            // the page (app.js appShell): "fullscreen" = toggle (key beside the logo, F11), "power-off" = MAIN switch
            cw.WebMessageReceived += (s, e) =>
            {
                string m;
                try { m = e.TryGetWebMessageAsString(); } catch (Exception) { return; }
                if (m == "fullscreen") SetFullScreen(!fullScreen);
                else if (m == "power-off") ExitAll();
                else if (m == "setup-done") LeaveSetup();
                else if (m == "start-server") StartServer();
                else if (m == "hello") TellFullScreen();
                else if (m.StartsWith("aspect:")) SetAspect(m.Substring(7));
            };
        }

        void TellFullScreen()
        {
            try
            {
                if (webOk && web.CoreWebView2 != null) web.CoreWebView2.PostWebMessageAsString(fullScreen ? "fullscreen:1" : "fullscreen:0");
            }
            catch (Exception) { }
        }

        bool IsLocal(string uri)
        {
            Uri u;
            if (!Uri.TryCreate(uri, UriKind.Absolute, out u)) return false;
            return (u.Port == port || u.Port == SetupPort) && (u.Host == "localhost" || u.Host == "127.0.0.1");
        }

        // full screen: no frame, over the taskbar, on the monitor the window is on; remembered in window.txt
        bool fullScreen;
        bool startFull;                       // full screen at the last exit (window.txt)
        public static bool StartFullArg;      // RADIMCOM.exe --fullscreen
        FormWindowState savedState = FormWindowState.Normal;

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            if (startFull || StartFullArg) SetFullScreen(true);
        }
        void SetFullScreen(bool on)
        {
            if (on == fullScreen) { TellFullScreen(); return; }
            fullScreen = on;
            if (on)
            {
                savedState = WindowState == FormWindowState.Minimized ? lastState : WindowState;
                FormBorderStyle = FormBorderStyle.None;
                WindowState = FormWindowState.Normal;     // a maximized window does not grow over the taskbar
                Bounds = Screen.FromControl(this).Bounds;
            }
            else
            {
                FormBorderStyle = FormBorderStyle.Sizable;
                WindowState = FormWindowState.Normal;
                Bounds = lastBounds;
                if (savedState == FormWindowState.Maximized) WindowState = FormWindowState.Maximized;
            }
            SetWindowIcons();
            TellFullScreen();
        }

        // ---- icon: radimcom.ico is embedded (csc -resource); the taskbar and title icons are set with WM_SETICON,
        // because WinForms leaves them out for a window without a border (full screen) and the taskbar then shows its default
        [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr hwnd, int msg, IntPtr wp, IntPtr lp);
        Icon bigIcon, smallIcon;

        static Icon AppIcon(int size)
        {
            try
            {
                using (var st = typeof(Shell).Assembly.GetManifestResourceStream("radimcom.ico"))
                    if (st != null) return new Icon(st, size, size);
            }
            catch (Exception) { }
            try { return Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch (Exception) { return null; }
        }

        void SetWindowIcons()
        {
            try
            {
                float scale = 1f;
                using (var g = CreateGraphics()) scale = g.DpiX / 96f;
                if (bigIcon == null) bigIcon = AppIcon((int)Math.Round(32 * scale));
                if (smallIcon == null) smallIcon = AppIcon((int)Math.Round(16 * scale));
                if (bigIcon != null) SendMessage(Handle, 0x0080, new IntPtr(1), bigIcon.Handle);      // WM_SETICON, ICON_BIG
                if (smallIcon != null) SendMessage(Handle, 0x0080, IntPtr.Zero, smallIcon.Handle);    // ICON_SMALL
            }
            catch (Exception) { }
        }

        void ReadPort()
        {
            // the port of the page: "port" in vfos.json (launcher), without vfos.json in config.json (one receiver)
            foreach (var f in new[] { "vfos.json", "config.json" })
            {
                try
                {
                    string path = Program.Data(f);
                    if (!File.Exists(path)) continue;
                    var d = new JavaScriptSerializer().DeserializeObject(File.ReadAllText(path)) as Dictionary<string, object>;
                    object v;
                    if (d != null && d.TryGetValue("port", out v)) port = Convert.ToInt32(v);
                    return;
                }
                catch (Exception) { }
            }
        }

        static bool Answers(int port, int timeoutMs)
        {
            try
            {
                var req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/");
                req.Timeout = timeoutMs;
                req.Proxy = null;
                using (var r = (HttpWebResponse)req.GetResponse()) return (int)r.StatusCode < 500;
            }
            catch (WebException ex)
            {
                return ex.Response != null;      // an HTTP error is still a running server
            }
            catch (Exception) { return false; }
        }

        async Task StartOrAttach()
        {
            ready = false;
            Page(Html("Starting RADIMCOM…", "The receivers open their SDR dongles.", true));
            int p = port;
            if (await Task.Run(() => Answers(p, 800)))
            {
                ownServer = false;               // already running (start.bat, another user session …): just show it
                tray.Text = "RADIMCOM (server started elsewhere)";
            }
            else
            {
                ownServer = true;
                try { server.Start(); }
                catch (Exception ex)
                {
                    Page(Html("RADIMCOM could not start", "Python: " + Server.Python() + "\n" + ex.Message, false));
                    return;
                }
                var sw = Stopwatch.StartNew();
                while (true)
                {
                    if (!server.Running) return;     // ServerExited shows why
                    if (await Task.Run(() => Answers(p, 1000))) break;
                    if (sw.Elapsed.TotalSeconds > 120)
                    {
                        Page(Html("RADIMCOM does not answer", "The server is running but its page does not answer on port "
                                  + port + ".\n\n" + server.Tail(), false));
                        return;
                    }
                    await Task.Delay(400);
                }
                tray.Text = "RADIMCOM";
            }
            ready = true;
            if (webOk) { if (Visible) Home(); }
            else if (initDoneWeb && !startHidden) OpenUrl(Url);
        }

        bool initDoneWeb { get { return web != null && !Controls.Contains(web); } }    // InitWeb failed

        void ServerExited(int code)
        {
            if (server.Stopping || exiting) return;
            Page(Html("The RADIMCOM server has ended", "Exit code " + code + ". Its output (also in data\\server_logs):\n\n"
                      + server.Tail(), false));
            ShowWindow();
        }

        void Page(string html)
        {
            status = html;
            if (html.Contains("<pre>")) ready = false;
            if (webOk && web != null && web.CoreWebView2 != null) web.CoreWebView2.NavigateToString(html);
        }

        static string Esc(string s)
        {
            return (s ?? "").Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;");
        }

        string Html(string title, string text, bool busy)
        {
            return "<!doctype html><html><head><meta charset='utf-8'><style>"
                + "html,body{margin:0;height:100%;background:#0a1422;color:#dfe8f3;font:15px system-ui,Segoe UI,sans-serif}"
                + "main{max-width:820px;margin:0 auto;padding:12vh 24px 24px}h1{font-weight:600;font-size:22px;color:#ffd84a}"
                + "pre{white-space:pre-wrap;background:#06101c;border:1px solid #1d3352;border-radius:6px;padding:12px;font:12px Consolas,monospace;color:#b9c7d8;max-height:50vh;overflow:auto}"
                + ".sp{width:28px;height:28px;border:3px solid #1d3352;border-top-color:#ffd84a;border-radius:50%;animation:r 1s linear infinite;margin-bottom:18px}"
                + "@keyframes r{to{transform:rotate(360deg)}}a{color:#ffb547}</style></head><body><main>"
                + (busy ? "<div class='sp'></div>" : "")
                + "<h1>" + Esc(title) + "</h1>" + (busy ? "<p>" + Esc(text) + "</p>" : "<pre>" + Esc(text) + "</pre>"
                + "<p>Restart it from the tray icon (right click → Restart server).</p>")
                + "</main></body></html>";
        }

        void ShowWindow()
        {
            if (exiting) return;
            startHidden = false;
            if (!Visible)
            {
                Show();
                Home();
            }
            if (WindowState == FormWindowState.Minimized) WindowState = lastState;
            Activate();
            BringToFront();
        }

        // ---- the window keeps the aspect ratio of the page (app.js fitStage sends "aspect:<w>:<h>" of its stage):
        // dragging an edge or a corner changes the other side with it; a new ratio (VIEW hides the lower part) sets
        // the height to the width. Maximized and full screen are not limited.
        double aspect;
        [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }

        void SetAspect(string v)
        {
            var p = v.Split(':');
            double w, h;
            if (p.Length != 2 || !double.TryParse(p[0], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out w)
                || !double.TryParse(p[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out h)
                || w <= 0 || h <= 0) return;
            double a = w / h;
            if (aspect > 0 && Math.Abs(a - aspect) / aspect < 0.005) return;
            aspect = a;
            FitAspect();
        }

        bool fitting;
        void FitAspect()        // height to the width (or narrower when too high for the screen)
        {
            if (aspect <= 0 || fitting || WindowState != FormWindowState.Normal || fullScreen || !Visible) return;
            if (ClientSize.Height > 0 && Math.Abs((double)ClientSize.Width / ClientSize.Height - aspect) / aspect < 0.01) return;
            fitting = true;
            try { FitAspectNow(); } finally { fitting = false; }
        }

        void FitAspectNow()
        {
            int ch = (int)Math.Round(ClientSize.Width / aspect);
            var wa = Screen.FromControl(this).WorkingArea;
            int ncH = Height - ClientSize.Height, ncW = Width - ClientSize.Width;
            if (ch + ncH > wa.Height)         // too high for the screen: narrower instead
            {
                ch = wa.Height - ncH;
                ClientSize = new Size((int)Math.Round(ch * aspect), ch);
            }
            else ClientSize = new Size(ClientSize.Width, ch);
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == 0x0214 && aspect > 0 && !fullScreen && WindowState == FormWindowState.Normal)    // WM_SIZING
            {
                var r = (RECT)Marshal.PtrToStructure(m.LParam, typeof(RECT));
                int ncW = Width - ClientSize.Width, ncH = Height - ClientSize.Height;
                int edge = m.WParam.ToInt32();
                int cw = r.Right - r.Left - ncW, ch = r.Bottom - r.Top - ncH;
                if (edge == 3 || edge == 6) cw = (int)Math.Round(ch * aspect);       // top / bottom: the width follows
                else ch = (int)Math.Round(cw / aspect);                               // left / right / corners: the height
                if (edge == 1 || edge == 4 || edge == 7) r.Left = r.Right - cw - ncW; else r.Right = r.Left + cw + ncW;
                if (edge == 3 || edge == 4 || edge == 5) r.Top = r.Bottom - ch - ncH; else r.Bottom = r.Top + ch + ncH;
                Marshal.StructureToPtr(r, m.LParam, false);
                m.Result = new IntPtr(1);
                return;
            }
            base.WndProc(ref m);
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            if (WindowState != FormWindowState.Minimized) lastState = WindowState;
            if (WindowState == FormWindowState.Normal && Visible && !fullScreen) lastBounds = Bounds;
            // restored from maximized / full screen, Aero snap...: back to the ratio of the page (not during a drag,
            // WM_SIZING keeps it there)
            if (WindowState == FormWindowState.Normal && aspect > 0 && !fitting && IsHandleCreated)
                BeginInvoke(new Action(FitAspect));
        }

        protected override void OnMove(EventArgs e)
        {
            base.OnMove(e);
            if (WindowState == FormWindowState.Normal && Visible && !fullScreen) lastBounds = Bounds;
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            SavePlacement();
            if (!exiting && e.CloseReason == CloseReason.UserClosing && setupMode)
            {
                // closing the SDR setup = cancel: the receiver starts with the settings it had, in the tray
                e.Cancel = true;
                Hide();
                LeaveSetup();
                return;
            }
            if (!exiting && e.CloseReason == CloseReason.UserClosing && ownServer)   // running or stopped from the tray
            {
                // the window closes, the server stays in the tray; the page stops (no sound, no polling)
                e.Cancel = true;
                Hide();
                if (webOk && web.CoreWebView2 != null) web.CoreWebView2.Navigate("about:blank");
                if (!trayHintShown)
                {
                    trayHintShown = true;
                    tray.ShowBalloonTip(4000, "RADIMCOM runs on", "The server keeps running in the tray (decoders, recordings). "
                                        + "Right click the icon → Exit RADIMCOM to stop it.", ToolTipIcon.Info);
                }
                return;
            }
            if (!exiting)
            {
                e.Cancel = true;
                ExitAll();
                return;
            }
            base.OnFormClosing(e);
        }

        void ExitAll()
        {
            if (exiting) return;
            exiting = true;
            SavePlacement();
            Hide();
            tray.Text = "RADIMCOM: stopping…";
            if (webOk && web.CoreWebView2 != null) web.CoreWebView2.Navigate("about:blank");
            var t = new Thread(() =>
            {
                if (setupServer.Running) setupServer.Stop(3000);
                if (ownServer) server.Stop(20000);
                BeginInvokeSafe(() => { tray.Visible = false; Application.Exit(); });
            });
            t.IsBackground = true;
            t.Start();
        }

        bool busy;                   // a start / stop is under way (the tray menu waits)

        void StartServer()
        {
            if (setupMode || busy || exiting || (ownServer && server.Running)) { ShowWindow(); return; }
            ShowWindow();
            busy = true;
            BeginInvokeSafe(async () => { try { await StartOrAttach(); } finally { busy = false; } });
        }

        /// <summary>Stops the receivers (the dongles are free, e.g. for another program); RADIMCOM.exe stays in the tray.</summary>
        void StopServer()
        {
            if (setupMode || busy || !ownServer || !server.Running) return;
            busy = true;
            ready = false;
            Page(Html("Stopping the RADIMCOM server…", "The receivers close their SDR dongles.", true));
            tray.Text = "RADIMCOM: stopping…";
            var t = new Thread(() =>
            {
                server.Stop(20000);
                BeginInvokeSafe(() =>
                {
                    busy = false;
                    tray.Text = "RADIMCOM (server stopped)";
                    Page(StoppedHtml());
                });
            });
            t.IsBackground = true;
            t.Start();
        }

        string StoppedHtml()
        {
            return Html("The RADIMCOM server is stopped", "The SDR dongles are free.", false)
                .Replace("<pre>The SDR dongles are free.</pre><p>Restart it from the tray icon (right click → Restart server).</p>",
                         "<p>The SDR dongles are free. Start it again here or from the tray icon (right click → Start server).</p>"
                         + "<p><button onclick=\"window.chrome.webview.postMessage('start-server')\" style=\"font:700 13px system-ui;"
                         + "padding:8px 16px;border-radius:4px;border:1px solid #f3cf55;color:#1a1400;cursor:pointer;"
                         + "background:linear-gradient(180deg,#ffe27a,#e8b928)\">START SERVER</button></p>");
        }

        void RestartServer()
        {
            if (setupMode) { LeaveSetup(); return; }
            if (!ownServer)
            {
                MessageBox.Show(this, "The server was started elsewhere (start.bat?); restart it there.", "RADIMCOM");
                return;
            }
            Page(Html("Restarting RADIMCOM…", "Stopping the server.", true));
            var t = new Thread(() =>
            {
                server.Stop(20000);
                BeginInvokeSafe(async () => { await StartOrAttach(); });
            });
            t.IsBackground = true;
            t.Start();
        }

        void OpenLog()
        {
            try
            {
                var dir = new DirectoryInfo(Program.Data("server_logs"));
                FileInfo newest = null;
                foreach (var f in dir.GetFiles("*.log"))
                    if (newest == null || f.LastWriteTimeUtc > newest.LastWriteTimeUtc) newest = f;
                if (newest != null) OpenPath(newest.FullName);
                else OpenPath(dir.FullName);
            }
            catch (Exception) { OpenPath(Path.Combine(Program.Base, "data")); }
        }

        static void OpenUrl(string url) { OpenPath(url); }

        static void OpenPath(string p)
        {
            try { Process.Start(new ProcessStartInfo(p) { UseShellExecute = true }); } catch (Exception) { }
        }

        string PlacementFile { get { return Program.Data("window.txt"); } }

        void LoadPlacement()
        {
            var wa = Screen.PrimaryScreen.WorkingArea;
            Bounds = new Rectangle(wa.X + wa.Width / 10, wa.Y + wa.Height / 12, wa.Width * 8 / 10, wa.Height * 10 / 12);
            try
            {
                var v = File.ReadAllText(PlacementFile).Trim().Split(' ');
                var r = new Rectangle(int.Parse(v[0]), int.Parse(v[1]), int.Parse(v[2]), int.Parse(v[3]));
                foreach (var s in Screen.AllScreens)
                    if (s.WorkingArea.IntersectsWith(new Rectangle(r.X + 40, r.Y + 10, Math.Max(r.Width - 80, 1), 30)))
                    {
                        Bounds = r;
                        break;
                    }
                if (Array.IndexOf(v, "max") > 3) WindowState = FormWindowState.Maximized;
                if (Array.IndexOf(v, "full") > 3) startFull = true;
            }
            catch (Exception) { }
            lastBounds = Bounds;
        }

        void SavePlacement()
        {
            try
            {
                if (lastBounds.Width < 100) return;
                Directory.CreateDirectory(Path.GetDirectoryName(PlacementFile));
                File.WriteAllText(PlacementFile, lastBounds.X + " " + lastBounds.Y + " " + lastBounds.Width + " " + lastBounds.Height
                                  + ((fullScreen ? savedState : WindowState) == FormWindowState.Maximized || (!fullScreen && lastState == FormWindowState.Maximized) ? " max" : "")
                                  + (fullScreen ? " full" : ""));
            }
            catch (Exception) { }
        }
    }
}

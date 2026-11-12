// "Price Tracker.exe": starts Price Tracker if it isn't running, then opens it in the browser.
//
// A tiny launcher: it runs scripts\open_app.pyw with the project's own Python (pythonw.exe,
// no console window), which does the real work (see that file). Keeping the logic in one
// Python file means the .exe never needs rebuilding when the app changes.
//
// The .exe must stay in the project folder (next to .venv and scripts). Build it with:
//     powershell -ExecutionPolicy Bypass -File scripts\build_launcher.ps1
//
// "Price Tracker.exe --check" exits with 0 when everything it needs is in place (no window).

using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("Price Tracker")]
[assembly: AssemblyProduct("Price Tracker")]
[assembly: AssemblyDescription("Starts Price Tracker and opens it in the browser")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

static class PriceTrackerLauncher
{
    [STAThread]
    static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string pythonw = Path.Combine(root, @".venv\Scripts\pythonw.exe");
        string script = Path.Combine(root, @"scripts\open_app.pyw");
        bool ready = File.Exists(pythonw) && File.Exists(script);

        if (args.Length > 0 && args[0] == "--check")
        {
            return ready ? 0 : 1;
        }
        if (!ready)
        {
            MessageBox.Show(
                "Price Tracker.exe must stay in the Price Tracker project folder, next to the .venv and " +
                "scripts folders.\n\nIf you want it on your desktop, use a shortcut instead of a copy " +
                "(scripts\\create_shortcut.ps1 makes one).\n\nLooked for:\n" + pythonw + "\n" + script,
                "Price Tracker", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 1;
        }

        var start = new ProcessStartInfo(pythonw, "\"" + script + "\"")
        {
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        try
        {
            Process.Start(start);  // open_app.pyw starts the server if needed, then the browser
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show("Couldn't start Price Tracker:\n\n" + error.Message,
                "Price Tracker", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

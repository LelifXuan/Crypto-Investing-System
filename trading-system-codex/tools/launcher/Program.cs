using System.Diagnostics;
using System.Net.Sockets;
using System.Windows.Forms;

static bool IsPortOpen(string host, int port)
{
    try
    {
        using var client = new TcpClient();
        var connectTask = client.ConnectAsync(host, port);
        var completed = connectTask.Wait(TimeSpan.FromMilliseconds(600));
        return completed && client.Connected;
    }
    catch
    {
        return false;
    }
}

static void OpenBrowser(string url)
{
    Process.Start(new ProcessStartInfo
    {
        FileName = url,
        UseShellExecute = true,
    });
}

var launcherDir = AppContext.BaseDirectory;
var projectDir = Path.Combine(launcherDir, "trading-system-codex");
var startScript = Path.Combine(projectDir, "start_portable.bat");
var appUrl = "http://127.0.0.1:8000/dashboard";

if (!Directory.Exists(projectDir) || !File.Exists(startScript))
{
    MessageBox.Show(
        $"未找到项目目录或启动脚本：\n{projectDir}\n{startScript}",
        "Trading System Launcher",
        MessageBoxButtons.OK,
        MessageBoxIcon.Error
    );
    return;
}

if (!IsPortOpen("127.0.0.1", 8000))
{
    try
    {
        Process.Start(new ProcessStartInfo
        {
            FileName = startScript,
            WorkingDirectory = projectDir,
            UseShellExecute = true,
            WindowStyle = ProcessWindowStyle.Normal,
        });
    }
    catch (Exception ex)
    {
        MessageBox.Show(
            $"启动应用失败：\n{ex.Message}",
            "Trading System Launcher",
            MessageBoxButtons.OK,
            MessageBoxIcon.Error
        );
        return;
    }

    for (var attempt = 0; attempt < 30; attempt++)
    {
        Thread.Sleep(1000);
        if (IsPortOpen("127.0.0.1", 8000))
        {
            break;
        }
    }
}

if (!IsPortOpen("127.0.0.1", 8000))
{
    MessageBox.Show(
        "应用启动超时。请检查 Python 环境、端口占用或项目日志。",
        "Trading System Launcher",
        MessageBoxButtons.OK,
        MessageBoxIcon.Warning
    );
    return;
}

OpenBrowser(appUrl);

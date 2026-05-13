using System.Diagnostics;
using System.Net.Http;
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

static bool IsHealthOk(string baseUrl)
{
    try
    {
        using var client = new HttpClient
        {
            Timeout = TimeSpan.FromMilliseconds(900),
        };
        var response = client.GetAsync($"{baseUrl}/health").GetAwaiter().GetResult();
        return response.IsSuccessStatusCode;
    }
    catch
    {
        return false;
    }
}

static string ResolveBundleRoot()
{
    var launcherDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
    var directStartScript = Path.Combine(launcherDir, "start_portable.bat");
    if (File.Exists(directStartScript))
    {
        return launcherDir;
    }

    var nestedRoot = Path.Combine(launcherDir, "trading-system-codex");
    if (File.Exists(Path.Combine(nestedRoot, "start_portable.bat")))
    {
        return nestedRoot;
    }

    var parentRoot = Directory.GetParent(launcherDir)?.FullName;
    if (parentRoot is not null && File.Exists(Path.Combine(parentRoot, "start_portable.bat")))
    {
        return parentRoot;
    }

    return launcherDir;
}

static int ReadPort(string bundleRoot)
{
    var envPath = Path.Combine(bundleRoot, "runtime", "config", "portable.env");
    if (!File.Exists(envPath))
    {
        return 8000;
    }

    foreach (var line in File.ReadAllLines(envPath))
    {
        var trimmed = line.Trim();
        if (!trimmed.StartsWith("APP_PORT=", StringComparison.OrdinalIgnoreCase))
        {
            continue;
        }
        if (int.TryParse(trimmed["APP_PORT=".Length..], out var port))
        {
            return port;
        }
    }
    return 8000;
}

var bundleRoot = ResolveBundleRoot();
var startScript = Path.Combine(bundleRoot, "start_portable.bat");
var embeddedPython = Path.Combine(bundleRoot, "runtime_env", "python", "python.exe");
var port = ReadPort(bundleRoot);
var baseUrl = $"http://127.0.0.1:{port}";
var appUrl = $"{baseUrl}/strategy-page";

if (!Directory.Exists(bundleRoot) || !File.Exists(startScript))
{
    MessageBox.Show(
        $"未找到便携包根目录或启动脚本：\n{bundleRoot}\n{startScript}",
        "Trading System Launcher",
        MessageBoxButtons.OK,
        MessageBoxIcon.Error
    );
    return;
}

if (!File.Exists(embeddedPython))
{
    MessageBox.Show(
        $"未找到内置 Python 运行时：\n{embeddedPython}\n\n请使用包含 runtime_env\\python 的 win-x64 便携包，或直接运行 start_portable.bat 查看详细日志。",
        "Trading System Launcher",
        MessageBoxButtons.OK,
        MessageBoxIcon.Error
    );
    return;
}

if (!IsHealthOk(baseUrl))
{
    try
    {
        Process.Start(new ProcessStartInfo
        {
            FileName = startScript,
            WorkingDirectory = bundleRoot,
            UseShellExecute = true,
            WindowStyle = ProcessWindowStyle.Normal,
        });
    }
    catch (Exception ex)
    {
        MessageBox.Show(
            $"应用启动失败：\n{ex.Message}",
            "Trading System Launcher",
            MessageBoxButtons.OK,
            MessageBoxIcon.Error
        );
        return;
    }

    for (var attempt = 0; attempt < 90; attempt++)
    {
        Thread.Sleep(1000);
        if (IsHealthOk(baseUrl))
        {
            break;
        }
    }
}

if (!IsHealthOk(baseUrl))
{
    var logPath = Path.Combine(bundleRoot, "runtime", "logs", "portable_console.log");
    var portHint = IsPortOpen("127.0.0.1", port)
        ? $"端口 {port} 已打开，但 /health 未返回正常状态，可能不是本应用。"
        : $"端口 {port} 未打开。";
    MessageBox.Show(
        $"应用启动超时。\n\n{portHint}\n\n请检查：\n1. 是否重复启动了旧版本程序；\n2. runtime_env\\python 是否完整；\n3. 启动日志：\n{logPath}\n\n也可以双击 start_portable.bat 查看控制台错误。",
        "Trading System Launcher",
        MessageBoxButtons.OK,
        MessageBoxIcon.Warning
    );
    return;
}

OpenBrowser(appUrl);

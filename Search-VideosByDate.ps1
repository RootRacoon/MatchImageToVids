<#
.SYNOPSIS
    Super-fast search for video files across ALL drives within a date range.

.DESCRIPTION
    Two engines, auto-selected:
      1. Everything (es.exe) - INSTANT. Reads the NTFS index of every drive.
         Install Everything + the "es" command-line tool from voidtools.com,
         then either put es.exe on your PATH or pass -EsPath.
      2. Native fallback - .NET enumeration across all ready drives. Slower
         than Everything but needs nothing installed.

.PARAMETER Start
    Start of the date range (inclusive). e.g. "2024-01-01" or "2024-01-01 08:00".

.PARAMETER End
    End of the date range (inclusive). e.g. "2024-06-30". A date with no time
    is treated as end-of-day (23:59:59) so the whole day is included.

.PARAMETER DateField
    Which timestamp to filter on: Modified (default) or Created.

.PARAMETER Drives
    Optional. Limit to specific drives, e.g. -Drives C,D. Default: all drives.

.PARAMETER Csv
    Optional path to also write results as a CSV file.

.PARAMETER EsPath
    Optional full path to es.exe if it isn't on your PATH.

.EXAMPLE
    .\Search-VideosByDate.ps1 -Start 2024-01-01 -End 2024-06-30

.EXAMPLE
    .\Search-VideosByDate.ps1 -Start 2025-05-01 -End 2025-05-31 -DateField Created -Csv results.csv
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [datetime] $Start,
    [Parameter(Mandatory = $true)] [datetime] $End,
    [ValidateSet('Modified', 'Created')] [string] $DateField = 'Modified',
    [string[]] $Drives,
    [string] $Csv,
    [string] $EsPath
)

# --- Video extensions to match ------------------------------------------------
$VideoExt = @(
    'mp4','mkv','avi','mov','wmv','flv','webm','m4v','mpg','mpeg',
    'm2ts','mts','ts','3gp','vob','ogv','rm','rmvb','divx','asf','f4v'
)

# If End has no time component, extend it to the end of that day.
if ($End.TimeOfDay -eq [timespan]::Zero) {
    $End = $End.Date.AddDays(1).AddSeconds(-1)
}

Write-Host "Searching $DateField dates $($Start.ToString('yyyy-MM-dd HH:mm')) .. $($End.ToString('yyyy-MM-dd HH:mm'))" -ForegroundColor Cyan

# --- Locate es.exe (Everything CLI) -------------------------------------------
function Resolve-Es {
    param([string] $Explicit)
    if ($Explicit -and (Test-Path $Explicit)) { return (Resolve-Path $Explicit).Path }
    $cmd = Get-Command es.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @("$env:ProgramFiles\Everything\es.exe",
                     "${env:ProgramFiles(x86)}\Everything\es.exe",
                     "$env:LOCALAPPDATA\Programs\Everything\es.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$es = Resolve-Es -Explicit $EsPath

# =============================================================================
# ENGINE 1: Everything (es.exe) - fastest path
# =============================================================================
function Search-WithEverything {
    param([string] $Es)

    Write-Host "Engine: Everything (es.exe) - $Es" -ForegroundColor Green

    $extQuery  = 'ext:' + ($VideoExt -join ';')
    $dateKind  = if ($DateField -eq 'Created') { 'dc' } else { 'dm' }
    # Everything date range syntax: dm:2024-01-01..2024-06-30
    $dateQuery = "{0}:{1}..{2}" -f $dateKind, $Start.ToString('yyyy-MM-dd'), $End.ToString('yyyy-MM-dd')

    $query = "file: $extQuery $dateQuery"
    if ($Drives) {
        # Restrict to given drive letters, e.g.  path:C:\ | path:D:\
        $paths = ($Drives | ForEach-Object { "path:$($_.TrimEnd(':','\'))" }) -join ' | '
        $query = "$query <$paths>"
    }

    # -csv output with the columns we want; parse it back into objects.
    $raw = & $Es -csv -size -date-modified -date-created -sort ($dateKind -eq 'dc' ? 'date-created' : 'date-modified') $query
    if (-not $raw) { return @() }

    $raw | ConvertFrom-Csv | ForEach-Object {
        [pscustomobject]@{
            Path     = $_.Filename
            SizeMB   = if ($_.Size) { [math]::Round(($_.Size -as [double]) / 1MB, 2) } else { $null }
            Modified = $_.'Date Modified'
            Created  = $_.'Date Created'
        }
    }
}

# =============================================================================
# ENGINE 2: Native .NET enumeration - fallback
# =============================================================================
function Search-Native {
    Write-Host "Engine: native .NET enumeration (Everything not found - install it for instant search)" -ForegroundColor Yellow

    $targetDrives =
        if ($Drives) {
            $Drives | ForEach-Object { Get-PSDrive ($_.TrimEnd(':','\')) -ErrorAction SilentlyContinue }
        } else {
            Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -ne $null -or $_.Used -ne $null }
        }
    $roots = $targetDrives | Where-Object { $_ } | ForEach-Object { $_.Root } | Sort-Object -Unique

    $extSet = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($e in $VideoExt) { [void]$extSet.Add('.' + $e) }

    $opts = [System.IO.EnumerationOptions]::new()
    $opts.RecurseSubdirectories = $true
    $opts.IgnoreInaccessible    = $true
    $opts.AttributesToSkip      = [System.IO.FileAttributes]::ReparsePoint

    $results = New-Object System.Collections.Generic.List[object]

    foreach ($root in $roots) {
        Write-Host "  scanning $root ..." -ForegroundColor DarkGray
        try {
            foreach ($file in [System.IO.Directory]::EnumerateFiles($root, '*', $opts)) {
                $ext = [System.IO.Path]::GetExtension($file)
                if (-not $extSet.Contains($ext)) { continue }
                try {
                    $info = [System.IO.FileInfo]::new($file)
                    $stamp = if ($DateField -eq 'Created') { $info.CreationTime } else { $info.LastWriteTime }
                    if ($stamp -ge $Start -and $stamp -le $End) {
                        $results.Add([pscustomobject]@{
                            Path     = $file
                            SizeMB   = [math]::Round($info.Length / 1MB, 2)
                            Modified = $info.LastWriteTime
                            Created  = $info.CreationTime
                        })
                    }
                } catch { }
            }
        } catch {
            Write-Warning "Skipped $root : $($_.Exception.Message)"
        }
    }
    $results
}

# --- Run ----------------------------------------------------------------------
$sw = [System.Diagnostics.Stopwatch]::StartNew()

$results = if ($es) { Search-WithEverything -Es $es } else { Search-Native }

$sw.Stop()

$results = $results | Sort-Object { [datetime]($_.$DateField) } -ErrorAction SilentlyContinue

Write-Host ""
Write-Host ("Found {0} video file(s) in {1:N1}s" -f @($results).Count, $sw.Elapsed.TotalSeconds) -ForegroundColor Cyan

if ($Csv) {
    $results | Export-Csv -Path $Csv -NoTypeInformation -Encoding UTF8
    Write-Host "Saved CSV -> $Csv" -ForegroundColor Green
}

$results

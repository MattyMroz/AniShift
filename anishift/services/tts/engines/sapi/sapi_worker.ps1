param(
    [switch]$ListVoices,
    [string]$VoiceName = "",
    [ValidateRange(-10, 10)]
    [int]$Rate = 0,
    [ValidateRange(0, 100)]
    [int]$Volume = 100
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ProtocolVersion = 1
$MaximumMessageBytes = 262144
$Utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8

function Write-JsonLine {
    param([hashtable]$Payload)

    $line = ConvertTo-Json -InputObject $Payload -Compress -Depth 5
    [Console]::Out.WriteLine($line)
    [Console]::Out.Flush()
}

function Get-VoiceRecords {
    param([object]$Speaker)

    $records = @()
    foreach ($voice in $Speaker.GetVoices()) {
        $records += @{
            id = [string]$voice.Id
            name = [string]$voice.GetDescription()
        }
    }
    return $records
}

function Select-ExactVoice {
    param(
        [object]$Speaker,
        [string]$ExpectedName
    )

    foreach ($voice in $Speaker.GetVoices()) {
        if ([string]::Equals($voice.GetDescription(), $ExpectedName, [StringComparison]::OrdinalIgnoreCase)) {
            return $voice
        }
    }
    throw "Configured SAPI voice is unavailable in this worker architecture."
}

function Resolve-OwnedOutputPath {
    param([string]$RawPath)

    if ([string]::IsNullOrWhiteSpace($RawPath)) {
        throw "Output path is empty."
    }
    $fullPath = [IO.Path]::GetFullPath($RawPath)
    $file = New-Object IO.FileInfo($fullPath)
    $parent = $file.Directory
    if (
        $null -eq $parent -or
        $parent.Name -ne "clips" -or
        -not $file.Name.StartsWith(".clip-", [StringComparison]::Ordinal) -or
        -not $file.Name.EndsWith(".wav.tmp", [StringComparison]::Ordinal) -or
        -not $file.Exists
    ) {
        throw "Output path is outside the temporary clip contract."
    }
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Output path cannot be a reparse point."
    }
    if (($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Output directory cannot be a reparse point."
    }
    return $file.FullName
}

$speaker = $null
$selectedVoice = $null
try {
    $speaker = New-Object -ComObject SAPI.SpVoice
    if ($ListVoices) {
        Write-JsonLine @{
            protocol_version = $ProtocolVersion
            operation = "list_voices"
            ok = $true
            voices = @(Get-VoiceRecords -Speaker $speaker)
        }
        return
    }

    if ([string]::IsNullOrWhiteSpace($VoiceName)) {
        throw "VoiceName is required."
    }
    $selectedVoice = Select-ExactVoice -Speaker $speaker -ExpectedName $VoiceName
    $speaker.Voice = $selectedVoice
    $speaker.Rate = $Rate
    $speaker.Volume = $Volume

    while ($null -ne ($line = [Console]::In.ReadLine())) {
        $requestId = "invalid"
        try {
            if ($Utf8.GetByteCount($line) -gt $MaximumMessageBytes) {
                throw "Request exceeds the IPC message limit."
            }
            $request = ConvertFrom-Json -InputObject $line
            if ($null -eq $request) {
                throw "Request is empty."
            }
            if ($request.request_id -isnot [string] -or [string]::IsNullOrWhiteSpace($request.request_id)) {
                throw "Request id is invalid."
            }
            $requestId = [string]$request.request_id
            if ($request.protocol_version -ne $ProtocolVersion) {
                throw "Protocol version is unsupported."
            }
            if ($request.operation -ne "synthesize") {
                throw "Operation is unsupported."
            }
            if (-not [string]::Equals($request.voice_name, $VoiceName, [StringComparison]::Ordinal)) {
                throw "Request voice differs from the initialized worker voice."
            }
            if ($request.text -isnot [string] -or [string]::IsNullOrEmpty($request.text)) {
                throw "Synthesis text is invalid."
            }

            $outputPath = Resolve-OwnedOutputPath -RawPath ([string]$request.output_path)
            $stream = New-Object -ComObject SAPI.SpFileStream
            $previousOutput = $speaker.AudioOutputStream
            try {
                $stream.Open($outputPath, 3, $false)
                $speaker.AudioOutputStream = $stream
                [void]$speaker.Speak([string]$request.text, 0)
            }
            finally {
                $speaker.AudioOutputStream = $previousOutput
                $stream.Close()
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($stream)
            }
            Write-JsonLine @{
                protocol_version = $ProtocolVersion
                request_id = $requestId
                ok = $true
                output_path = $outputPath
            }
        }
        catch {
            [Console]::Error.WriteLine("SAPI worker request failed: {0}", $_.Exception.GetType().Name)
            Write-JsonLine @{
                protocol_version = $ProtocolVersion
                request_id = $requestId
                ok = $false
                error_code = "SAPI_SPEAK_FAILED"
                message = "SAPI synthesis failed."
            }
        }
    }
}
catch {
    [Console]::Error.WriteLine("SAPI worker initialization failed: {0}", $_.Exception.GetType().Name)
    if ($ListVoices) {
        Write-JsonLine @{
            protocol_version = $ProtocolVersion
            operation = "list_voices"
            ok = $false
            voices = @()
        }
    }
    exit 1
}
finally {
    if ($null -ne $selectedVoice) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($selectedVoice)
    }
    if ($null -ne $speaker) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($speaker)
    }
}

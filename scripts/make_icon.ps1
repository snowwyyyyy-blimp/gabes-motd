# Generates the site icon: assets/icon.svg, icon.png, icon-180.png, icon-32.png
# Run: powershell -ExecutionPolicy Bypass -File scripts\make_icon.ps1
param(
    [string]$OutDir = (Join-Path $PSScriptRoot '..\assets')
)

Add-Type -AssemblyName System.Drawing

$OutDir = (Resolve-Path $OutDir).Path
$bgColor     = [System.Drawing.Color]::FromArgb(255, 20, 23, 28)
$borderColor = [System.Drawing.Color]::FromArgb(255, 46, 55, 67)
$boltColor   = [System.Drawing.Color]::FromArgb(255, 76, 141, 255)
$wrenchColor = [System.Drawing.Color]::FromArgb(255, 255, 154, 60)
$outlineColor= [System.Drawing.Color]::FromArgb(255, 196, 103, 15)

function New-RoundedRect([float]$x, [float]$y, [float]$w, [float]$h, [float]$r) {
    $p = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $r * 2
    $p.AddArc($x, $y, $d, $d, 180, 90)
    $p.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
    $p.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
    $p.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
    $p.CloseFigure()
    return $p
}

# Open-end wrench head: outer arc, radial cut, inner arc back.
$cx = 256.0; $cy = 150.0; $ro = 82.0; $ri = 38.0; $gap = 58.0; $steps = 72
$start = -90.0 + ($gap / 2.0)
$sweep = 360.0 - $gap
$headPts = New-Object System.Collections.Generic.List[System.Drawing.PointF]
for ($i = 0; $i -le $steps; $i++) {
    $a = [Math]::PI / 180.0 * ($start + $sweep * $i / $steps)
    $headPts.Add([System.Drawing.PointF]::new(
        [float]($cx + $ro * [Math]::Cos($a)),
        [float]($cy + $ro * [Math]::Sin($a))))
}
for ($i = $steps; $i -ge 0; $i--) {
    $a = [Math]::PI / 180.0 * ($start + $sweep * $i / $steps)
    $headPts.Add([System.Drawing.PointF]::new(
        [float]($cx + $ri * [Math]::Cos($a)),
        [float]($cy + $ri * [Math]::Sin($a))))
}

$boltPts = @(
    [System.Drawing.PointF]::new(318, 60),
    [System.Drawing.PointF]::new(170, 292),
    [System.Drawing.PointF]::new(248, 292),
    [System.Drawing.PointF]::new(198, 450),
    [System.Drawing.PointF]::new(352, 212),
    [System.Drawing.PointF]::new(274, 212)
)

# ---------- SVG ----------

$headText = ($headPts | ForEach-Object { '{0:0.##},{1:0.##}' -f $_.X, $_.Y }) -join ' '
$svg = @"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="gabes little server!">
  <rect width="512" height="512" rx="92" fill="#14171c"/>
  <rect x="6" y="6" width="500" height="500" rx="86" fill="none" stroke="#2e3743" stroke-width="12"/>
  <polygon points="318,60 170,292 248,292 198,450 352,212 274,212" fill="#4c8dff"/>
  <g transform="rotate(-40 256 256)" stroke="#c4670f" stroke-width="12" stroke-linejoin="round">
    <rect x="229" y="150" width="54" height="280" rx="27" fill="#ff9a3c"/>
    <polygon points="$headText" fill="#ff9a3c"/>
  </g>
</svg>
"@
Set-Content -Path (Join-Path $OutDir 'icon.svg') -Value $svg -Encoding Ascii

# ---------- PNG ----------

$scale = 2
$size = 512 * $scale
$bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
$g.Clear([System.Drawing.Color]::Transparent)
$g.ScaleTransform($scale, $scale)

$bgBrush = New-Object System.Drawing.SolidBrush($bgColor)
$g.FillPath($bgBrush, (New-RoundedRect 0 0 512 512 92))

$borderPen = New-Object System.Drawing.Pen($borderColor, 12)
$g.DrawPath($borderPen, (New-RoundedRect 6 6 500 500 86))

$boltBrush = New-Object System.Drawing.SolidBrush($boltColor)
$g.FillPolygon($boltBrush, $boltPts)

$wrenchBrush = New-Object System.Drawing.SolidBrush($wrenchColor)
$outlinePen = New-Object System.Drawing.Pen($outlineColor, 12)
$outlinePen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round

$g.TranslateTransform(256, 256)
$g.RotateTransform(-40)
$g.TranslateTransform(-256, -256)

$handle = New-RoundedRect 229 150 54 280 27
$g.FillPath($wrenchBrush, $handle)
$g.DrawPath($outlinePen, $handle)

$headArr = $headPts.ToArray()
$g.FillPolygon($wrenchBrush, $headArr)
$g.DrawPolygon($outlinePen, $headArr)

function Save-Size([System.Drawing.Image]$source, [int]$px, [string]$path) {
    $b = New-Object System.Drawing.Bitmap($px, $px, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $gg = [System.Drawing.Graphics]::FromImage($b)
    $gg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $gg.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $gg.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $gg.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $gg.DrawImage($source, (New-Object System.Drawing.Rectangle(0, 0, $px, $px)))
    $b.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $gg.Dispose()
    $b.Dispose()
}

$icon512 = New-Object System.Drawing.Bitmap(512, 512, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g512 = [System.Drawing.Graphics]::FromImage($icon512)
$g512.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g512.DrawImage($bmp, (New-Object System.Drawing.Rectangle(0, 0, 512, 512)))
$g512.Dispose()
$icon512.Save((Join-Path $OutDir 'icon.png'), [System.Drawing.Imaging.ImageFormat]::Png)

Save-Size $icon512 180 (Join-Path $OutDir 'icon-180.png')
Save-Size $icon512 32 (Join-Path $OutDir 'icon-32.png')

$g.Dispose()
$bmp.Dispose()
$icon512.Dispose()

Get-ChildItem $OutDir -Filter 'icon*' | Select-Object Name, Length

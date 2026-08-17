# Read the full _build_stage_repair_agenda and _build_scene_repair_agenda functions
$filePath = "D:\Work\Project\screenplay-agent-refactor-v2\core\production_skill.py"
$content = Get-Content $filePath -Raw

# Find _build_stage_repair_agenda
$startIdx = $content.IndexOf("def _build_stage_repair_agenda(")
if ($startIdx -gt 0) {
    # Find the end of the function (next def at same level)
    $endIdx = $content.IndexOf("`ndef ", $startIdx + 10)
    if ($endIdx -eq -1) { $endIdx = $content.Length }
    $func1 = $content.Substring($startIdx, $endIdx - $startIdx)
    Write-Output "=== _build_stage_repair_agenda ==="
    Write-Output $func1
}

Write-Output "`n`n"

# Find _build_scene_repair_agenda
$startIdx2 = $content.IndexOf("def _build_scene_repair_agenda(")
if ($startIdx2 -gt 0) {
    $endIdx2 = $content.IndexOf("`ndef ", $startIdx2 + 10)
    if ($endIdx2 -eq -1) { $endIdx2 = $content.Length }
    $func2 = $content.Substring($startIdx2, $endIdx2 - $startIdx2)
    Write-Output "=== _build_scene_repair_agenda ==="
    Write-Output $func2
}

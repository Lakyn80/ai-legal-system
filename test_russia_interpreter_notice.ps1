<#
.SYNOPSIS
    Smoke test for dedicated Russian law API endpoints.
    Tests /api/russia/search and /api/russia/article.

.DESCRIPTION
    Uses the dedicated Russian endpoints (NOT /api/search/answer).
    Czech and Russian pipelines are intentionally separate.

.USAGE
    .\test_russia_interpreter_notice.ps1
    .\test_russia_interpreter_notice.ps1 -BaseUrl http://localhost:8032

.ENCODING NOTE
    Invoke-RestMethod with -Body (string) + ContentType "application/json" works
    correctly for Cyrillic on both PS 5.x and PS 7.x.
    Do NOT use [System.Text.Encoding]::UTF8.GetBytes($body) — that causes
    PowerShell 5.x to send a chunked body that triggers ResponseEnded errors.
    Instead: ConvertTo-Json produces ASCII-safe \uXXXX escapes automatically.
#>
param(
    [string]$BaseUrl = "http://localhost:8032"
)

$SearchEndpoint    = "/api/russia/search"
$ArticleEndpoint   = "/api/russia/article"
$IssueEndpoint     = "/api/russia/interpreter-issue"

# ---------------------------------------------------------------------------
# Search tests — POST /api/russia/search
# ---------------------------------------------------------------------------
#   Each entry: Name, Query, optional LawId, expected law_id in first result

$searchTests = @(
    @{
        Name   = "GPK čl. 9 — topic"
        Body   = @{ query = "гпк рф статья 9"; mode = "topic"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "GPK čl. 113 — notice/summons"
        Body   = @{ query = "надлежащее извещение сторон о судебном заседании"; law_id = "local:ru/gpk"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "GPK čl. 162 — interpreter"
        Body   = @{ query = "переводчик в гражданском процессе"; law_id = "local:ru/gpk"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Tlumočník v civilním procesu"
        Body   = @{ query = "переводчик в гражданском процессе"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Osoba neovládající jazyk řízení"
        Body   = @{ query = "лицо не владеющее языком судопроизводства"; law_id = "local:ru/gpk"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Právo na tlumočníka"
        Body   = @{ query = "право на переводчика"; law_id = "local:ru/gpk"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Jazyk soudního řízení"
        Body   = @{ query = "язык судопроизводства"; law_id = "local:ru/gpk"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Nebyl jsem oficiálně vyrozuměn"
        Body   = @{ query = "я не был официально уведомлен о судебном заседании"; law_id = "local:ru/gpk"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Nebyl jsem řádně předvolán"
        Body   = @{ query = "меня не вызвали в суд надлежащим образом"; law_id = "local:ru/gpk"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Soud jednal bez mého vyrozumění"
        Body   = @{ query = "суд рассмотрел дело без моего извещения"; law_id = "local:ru/gpk"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Cizinec bez tlumočníka"
        Body   = @{ query = "иностранный гражданин без переводчика в суде"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Rozhodnutí a dokumenty jen v ruštině"
        Body   = @{ query = "все документы и решение суда были только на русском языке"; law_id = "local:ru/gpk"; top_k = 3 }
        Expect = "local:ru/gpk"
    },
    @{
        Name   = "Podpůrná vrstva ECHR — přímý search"
        Body   = @{ query = "справедливое судебное разбирательство переводчик"; law_id = "local:ru/echr"; top_k = 3 }
        Expect = "local:ru/echr"
    },
    @{
        Name   = "Podpůrná vrstva FL-115 — přímý search"
        Body   = @{ query = "иностранец в российском суде"; law_id = "local:ru/fl115"; top_k = 3 }
        Expect = "local:ru/fl115"
    }
)

# ---------------------------------------------------------------------------
# Article lookup tests — GET /api/russia/article
# ---------------------------------------------------------------------------
$articleTests = @(
    @{ Name = "GPK čl. 9 (jazyk)";   LawId = "local:ru/gpk"; ArticleNum = "9";   ExpectHit = $true },
    @{ Name = "GPK čl. 113 (výzva)"; LawId = "local:ru/gpk"; ArticleNum = "113"; ExpectHit = $true },
    @{ Name = "GPK čl. 162 (tlumočník)"; LawId = "local:ru/gpk"; ArticleNum = "162"; ExpectHit = $true },
    @{ Name = "Neexistující článek"; LawId = "local:ru/gpk"; ArticleNum = "9999"; ExpectHit = $false }
)

# ---------------------------------------------------------------------------
# Interpreter-issue tests — POST /api/russia/interpreter-issue
# ---------------------------------------------------------------------------
$issueTests = @(
    @{
        Name         = "Tlumočník — subissue"
        Body         = @{ case_text = "иностранный гражданин не получил переводчика в суде" }
        ExpectIssue  = "interpreter_issue"
        ExpectMatch  = $true
    },
    @{
        Name         = "Jazyk řízení — subissue"
        Body         = @{ case_text = "я не понимал язык заседания" }
        ExpectIssue  = "language_issue"
        ExpectMatch  = $true
    },
    @{
        Name         = "Výzva — subissue"
        Body         = @{ case_text = "меня не вызвали в суд надлежащим образом" }
        ExpectIssue  = "notice_issue"
        ExpectMatch  = $true
    },
    @{
        Name         = "Kombinovaný případ"
        Body         = @{ case_text = "иностранец без переводчика и без официального вызова в суд" }
        ExpectIssue  = "interpreter_issue"
        ExpectMatch  = $true
    },
    @{
        Name         = "Žádná shoda"
        Body         = @{ case_text = "суд отказал в иске" }
        ExpectIssue  = $null
        ExpectMatch  = $false
    }
)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

function Invoke-JsonPost {
    param([string]$Uri, [hashtable]$Body)
    $json = $Body | ConvertTo-Json -Depth 5 -Compress
    return Invoke-RestMethod -Uri $Uri -Method POST -ContentType "application/json" -Body $json
}

function Get-FirstLawId($resp) {
    if ($null -eq $resp) { return $null }
    if ($resp.PSObject.Properties.Name -contains "results" -and $resp.results.Count -gt 0) {
        return $resp.results[0].law_id
    }
    return $null
}

function Get-ShortText($resp) {
    if ($null -eq $resp) { return "" }
    if ($resp.PSObject.Properties.Name -contains "results" -and $resp.results.Count -gt 0) {
        $t = $resp.results[0].text -replace "\s+", " "
        return $t.Substring(0, [Math]::Min(100, $t.Length))
    }
    return ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

$passed = 0
$failed = 0

Write-Host ""
Write-Host "=== Russian legal API smoke test ===" -ForegroundColor Cyan
Write-Host "Base URL : $BaseUrl"
Write-Host "Endpoints: $SearchEndpoint  |  $ArticleEndpoint  |  $IssueEndpoint"
Write-Host ""

# ── Search tests ──────────────────────────────────────────────────────────
Write-Host "--- POST $SearchEndpoint ---" -ForegroundColor DarkCyan
Write-Host ""

foreach ($t in $searchTests) {
    try {
        $resp = Invoke-JsonPost -Uri ($BaseUrl + $SearchEndpoint) -Body $t.Body
        $lawId = Get-FirstLawId $resp
        $preview = Get-ShortText $resp

        if ($lawId -eq $t.Expect) {
            Write-Host "[PASS] $($t.Name)" -ForegroundColor Green
            Write-Host "  law_id : $lawId | count: $($resp.result_count)"
            if ($preview) { Write-Host "  text   : $preview" }
            $passed++
        } else {
            Write-Host "[FAIL] $($t.Name)" -ForegroundColor Red
            Write-Host "  Expected : $($t.Expect)"
            Write-Host "  Actual   : $lawId"
            $failed++
        }
    } catch {
        Write-Host "[ERROR] $($t.Name)" -ForegroundColor Yellow
        Write-Host "  $_"
        $failed++
    }
    Write-Host ""
}

# ── Article tests ─────────────────────────────────────────────────────────
Write-Host "--- GET $ArticleEndpoint ---" -ForegroundColor DarkCyan
Write-Host ""

foreach ($t in $articleTests) {
    try {
        $uri = "$BaseUrl$ArticleEndpoint`?law_id=$([uri]::EscapeDataString($t.LawId))&article_num=$($t.ArticleNum)"
        $resp = Invoke-RestMethod -Uri $uri -Method GET

        $hit = $resp.hit
        if ($hit -eq $t.ExpectHit) {
            Write-Host "[PASS] $($t.Name)" -ForegroundColor Green
            Write-Host "  hit: $hit  art: $($resp.article_num)  chunks: $($resp.chunks.Count)"
            $passed++
        } else {
            Write-Host "[FAIL] $($t.Name)" -ForegroundColor Red
            Write-Host "  Expected hit=$($t.ExpectHit), got hit=$hit"
            $failed++
        }
    } catch {
        Write-Host "[ERROR] $($t.Name)" -ForegroundColor Yellow
        Write-Host "  $_"
        $failed++
    }
    Write-Host ""
}

# ── Interpreter-issue tests ───────────────────────────────────────────────
Write-Host "--- POST $IssueEndpoint ---" -ForegroundColor DarkCyan
Write-Host ""

foreach ($t in $issueTests) {
    try {
        $resp = Invoke-JsonPost -Uri ($BaseUrl + $IssueEndpoint) -Body $t.Body

        $matched   = $resp.is_matched
        $subissues = $resp.detected_subissues

        $matchOk  = ($matched -eq $t.ExpectMatch)
        $issueOk  = ($null -eq $t.ExpectIssue) -or ($subissues -contains $t.ExpectIssue)

        if ($matchOk -and $issueOk) {
            Write-Host "[PASS] $($t.Name)" -ForegroundColor Green
            Write-Host "  matched: $matched  subissues: $($subissues -join ', ')"
            if ($resp.primary_results.Count -gt 0) {
                $arts = ($resp.primary_results | ForEach-Object { "ст.$($_.article_num)" }) -join ", "
                Write-Host "  primary: $arts"
            }
            $passed++
        } else {
            Write-Host "[FAIL] $($t.Name)" -ForegroundColor Red
            Write-Host "  matched=$matched (expected $($t.ExpectMatch))"
            Write-Host "  subissues: $($subissues -join ', ')  (expected: $($t.ExpectIssue))"
            $failed++
        }
    } catch {
        Write-Host "[ERROR] $($t.Name)" -ForegroundColor Yellow
        Write-Host "  $_"
        $failed++
    }
    Write-Host ""
}

# ── Summary ───────────────────────────────────────────────────────────────
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Passed : $passed" -ForegroundColor Green
Write-Host "Failed : $failed" -ForegroundColor Red
Write-Host ""

if ($failed -gt 0) {
    exit 1
}

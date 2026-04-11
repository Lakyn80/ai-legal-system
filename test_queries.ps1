[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$PORT = 8032
$URL  = "http://localhost:$PORT/api/search/answer"

function Test-ContainsAny {
    param(
        [string]$Text,
        [string[]]$Needles
    )
    foreach ($needle in $Needles) {
        if ($Text.Contains($needle.ToLower())) {
            return $true
        }
    }
    return $false
}

function Test-ContainsForbidden {
    param(
        [string]$Text,
        [string[]]$Needles
    )
    foreach ($needle in $Needles) {
        if ($Text.Contains($needle.ToLower())) {
            return $needle
        }
    }
    return $null
}

function Test-IsStructuralText {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $true
    }

    if ($Text -match '^\d{1,3}\.\s+(?:z[aá]kon|na[rř][íi]zen[íi]|vyhl[áa][šs]ka|sd[eě]len[íi])') {
        return $true
    }

    if ($Text -match '^(?:část|hlava|díl|oddíl|pododdíl|kapitola)\b') {
        return $true
    }

    $words = [regex]::Matches($Text, '\w+', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    $lower = $Text.ToLower()
    $verbHints = @("je","jsou","má","ma","musí","musi","může","muze","lze","činí","cini","obsahuje","obsahovat","upravuje","vzniká","vznika","zaniká","zanika","trvá","trva")
    $hasVerb = $false
    foreach ($hint in $verbHints) {
        if ($lower.Contains($hint)) {
            $hasVerb = $true
            break
        }
    }

    if ($Text.Length -lt 120 -and $words.Count -le 12 -and $Text -notmatch '[.!?;:]' -and -not $hasVerb) {
        return $true
    }

    return $false
}

function Test-DocMatch {
    param(
        [string]$DocId,
        [string]$Expected
    )

    if ([string]::IsNullOrWhiteSpace($DocId) -or [string]::IsNullOrWhiteSpace($Expected)) {
        return $false
    }

    if ($DocId.Contains($Expected)) {
        return $true
    }

    $parts = $Expected.Split("/")
    if ($parts.Count -eq 2) {
        $iri = "local:sb/$($parts[1])/$($parts[0])"
        return $DocId.Contains($iri)
    }

    return $false
}

$rules = @{
    "§ 52 zákoník práce" = @{
        expectedDoc = "262/2006"
        requiredAny = @("výpověď", "důvody výpovědi", "zaměstnavatel")
        forbidden = @("okamžité zrušení pracovního poměru")
    }
    "zákon 500/2004 § 3" = @{
        expectedDoc = "500/2004"
        requiredAny = @("správní orgán", "správní orgány", "veřejný zájem", "dotčené osoby")
        forbidden = @("zaměstnavatel", "pracovní poměr", "výpověď")
    }
    "výpovědní doba zákoník práce" = @{
        expectedDoc = "262/2006"
        requiredAny = @("výpovědní doba", "2 měsíce", "dva měsíce")
        substantiveTop = $true
    }
    "pracovní smlouva zákoník práce náležitosti" = @{
        expectedDoc = "262/2006"
        requiredAny = @("pracovní smlouva musí obsahovat", "druh práce", "místo výkonu práce", "den nástupu")
        substantiveTop = $true
    }
    "kupní smlouva občanský zákoník" = @{
        expectedDoc = "89/2012"
        requiredAny = @("kupní smlouv", "prodávaj", "kupující", "koupě")
        forbidden = @("v poskytnutých úryvcích není", "v úryvcích není", "není relevantní ustanovení", "nebylo možné najít relevantní ustanovení")
        substantiveTop = $true
    }
}

$queries = @(
    # exact lookup
    "§ 52 zákoník práce",
    "§ 55 zákoník práce",
    "§ 56 zákoník práce",
    "§ 245 zákoník práce",
    "§ 89 občanský zákoník",
    "§ 2079 občanský zákoník",
    "§ 2910 občanský zákoník",
    "§ 209 trestní zákoník",
    "§ 140 trestní zákoník",
    "zákon 262/2006 § 52",
    "zákon 586/1992 § 6",
    "zákon 500/2004 § 3",
    "§ 6 zákon o daních z příjmů",
    "§ 1 zákon o daních z příjmů",
    # law constrained
    "výpověď zákoník práce",
    "výpovědní doba zákoník práce",
    "odstupné zákoník práce podmínky",
    "dovolená zákoník práce délka",
    "přesčas zákoník práce maximum",
    "pracovní smlouva zákoník práce náležitosti",
    "kupní smlouva občanský zákoník",
    "náhrada škody občanský zákoník",
    "nájemní smlouva byt",
    "trestní zákoník vražda trest",
    "správní řízení zákon 500/2004",
    # domain search
    "jak dlouho trvá výpovědní doba",
    "kdy může zaměstnavatel okamžitě zrušit pracovní poměr",
    "zaměstnanec nárok na odstupné",
    "jak se počítá dovolená",
    "zkušební doba délka",
    "mzda minimální výše",
    "rozvod manželství podmínky",
    "péče o dítě po rozvodu",
    "daňové přiznání termín podání",
    "trestný čin krádež sazba",
    "správní orgán přezkum rozhodnutí",
    "valná hromada akciová společnost",
    # broad / natural language
    "v práci mi neposkytli přestávku",
    "zaměstnavatel mi dluží mzdu",
    "jsem ve zkušební době co mohu",
    "nájem bytu práva nájemce",
    "ublížení na zdraví trestní odpovědnost",
    "kdy zaniká závazek",
    "co je kupní smlouva",
    # clarification (bare §)
    "§ 52",
    "§ 1",
    # irrelevant
    "počasí Praha zítra",
    "recept na svíčkovou",
    "python programming tutorial"
)

$pass = 0
$fail = 0
$errors = 0

Write-Host ("{0,-50} {1,-8} {2}" -f "QUERY", "STATUS", "DETAIL") -ForegroundColor Cyan
Write-Host ("-" * 110) -ForegroundColor DarkGray

foreach ($q in $queries) {
    $bodyObj = @{ query = $q; country = "czechia"; domain = "law"; top_k = 3 }
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes(($bodyObj | ConvertTo-Json -Compress))

    try {
        $resp = Invoke-RestMethod `
            -Uri $URL `
            -Method POST `
            -Body $bodyBytes `
            -ContentType "application/json; charset=utf-8" `
            -ErrorAction Stop

        $answerType  = $resp.response.answer_type
        $summary     = $resp.response.summary
        $explanation = $resp.response.explanation
        $topResult   = ($resp.results | Select-Object -First 1)
        $docIds      = $topResult.document_id
        $topText     = $topResult.text
        $topText     = if ($topText -and $topText.Length -gt 80) { $topText.Substring(0,80) + "..." } else { $topText }
        $score       = $topResult.score
        $status      = "PASS"
        $detail      = ""

        if ($rules.ContainsKey($q)) {
            $rule = $rules[$q]
            $answerText = ("$summary`n$explanation").ToLower()

            if (-not (Test-DocMatch -DocId $docIds -Expected $rule["expectedDoc"])) {
                $status = "FAIL"
                $detail = "expected doc $($rule["expectedDoc"]), got $docIds"
            }
            elseif ($rule.ContainsKey("substantiveTop") -and $rule["substantiveTop"] -and (Test-IsStructuralText -Text ($topResult.text))) {
                $status = "FAIL"
                $detail = "top chunk is structural"
            }
            elseif ($rule.ContainsKey("requiredAny") -and -not (Test-ContainsAny -Text $answerText -Needles $rule["requiredAny"])) {
                $status = "FAIL"
                $detail = "missing required explanation signal"
            }
            else {
                $forbidden = if ($rule.ContainsKey("forbidden")) { Test-ContainsForbidden -Text $answerText -Needles $rule["forbidden"] } else { $null }
                if ($forbidden) {
                    $status = "FAIL"
                    $detail = "forbidden phrase: $forbidden"
                }
            }
        }

        $color = if ($status -eq "PASS") { "Green" } else { "Red" }
        Write-Host ("{0,-50} {1,-8} {2}" -f $q.Substring(0,[Math]::Min(49,$q.Length)), $status, $detail) -ForegroundColor $color
        Write-Host ("  type       : $answerType  |  doc: $docIds  |  score: $([math]::Round($score,3))") -ForegroundColor DarkGray
        Write-Host ("  summary    : $summary") -ForegroundColor White
        Write-Host ("  explanation: $explanation") -ForegroundColor Gray
        Write-Host ("  top chunk  : $topText") -ForegroundColor DarkYellow
        Write-Host ""
        if ($status -eq "PASS") {
            $pass++
        }
        else {
            $fail++
        }
    }
    catch {
        Write-Host ("{0,-50} {1,-8} {2}" -f $q.Substring(0,[Math]::Min(49,$q.Length)), "ERROR", $_.Exception.Message.Substring(0,[Math]::Min(80,$_.Exception.Message.Length))) -ForegroundColor Red
        $errors++
    }
}

Write-Host ("-" * 110) -ForegroundColor DarkGray
Write-Host "TOTAL: $($queries.Count)   PASS: $pass   FAIL: $fail   ERRORS: $errors" -ForegroundColor Cyan

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$PORT = 8032
$URL  = "http://localhost:$PORT/api/search/answer"
$ExpectedDoc = "262/2006"

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
    $verbHints = @("je","jsou","má","ma","musí","musi","může","muze","lze","činí","cini","obsahuje","obsahovat","upravuje","vzniká","vznika","zaniká","zanika","trvá","trva","náleží","nalezi")
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
    "§ 34 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("pracovní smlouva", "druh práce", "místo výkonu práce", "den nástupu")
        substantiveTop = $true
    }
    "§ 35 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("zkušební doba", "delší než", "vedoucího zaměstnance")
        substantiveTop = $true
    }
    "§ 52 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("výpověď", "zaměstnavatel", "důvod")
        forbidden = @("kupní smlouva", "rozvod")
    }
    "§ 55 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("okamžitě zrušit", "pracovní poměr", "zaměstnavatel")
        substantiveTop = $true
    }
    "§ 56 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("zaměstnanec", "okamžitě zrušit", "pracovní poměr")
        substantiveTop = $true
    }
    "§ 66 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("zkušební době", "zaměstnavatel", "zaměstnanec")
        substantiveTop = $true
    }
    "§ 67 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("odstupné", "pracovního poměru", "výpovědí")
        substantiveTop = $true
    }
    "§ 88 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("přestávku", "jídlo", "oddech")
        substantiveTop = $true
    }
    "§ 141 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("splatná", "vykonání práce", "kalendářním měsíci")
        substantiveTop = $true
    }
    "§ 211 zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("dovolenou", "zaměstnanci", "za kalendářní rok")
        substantiveTop = $true
    }
    "zákon 262/2006 § 52" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("výpověď", "zaměstnavatel", "důvod")
        substantiveTop = $true
    }
    "výpovědní důvody zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("výpověď", "zaměstnavatel", "§ 52")
        substantiveTop = $true
    }
    "výpovědní doba zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("výpovědní doba", "2 měsíce", "dva měsíce")
        substantiveTop = $true
    }
    "odstupné zákoník práce podmínky" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("odstupné", "výpovědí", "§ 67")
        substantiveTop = $true
    }
    "pracovní smlouva zákoník práce náležitosti" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("pracovní smlouva musí obsahovat", "druh práce", "místo výkonu práce", "den nástupu")
        substantiveTop = $true
    }
    "dovolená zákoník práce délka" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("dovolená", "týdnů", "výměra")
        substantiveTop = $true
    }
    "přestávka v práci zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("přestávka", "jídlo", "oddech")
        substantiveTop = $true
    }
    "splatnost mzdy zákoník práce" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("mzda", "splatná", "kalendářním měsíci")
        substantiveTop = $true
    }
    "mám nárok na odstupné při nadbytečnosti" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("odstupné", "nadbytečnost", "§ 52", "§ 67")
        substantiveTop = $true
    }
    "kdy může zaměstnavatel dát výpověď" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("zaměstnavatel", "výpověď", "§ 52")
        substantiveTop = $true
    }
    "jak dlouhá je výpovědní doba" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("výpovědní doba", "2 měsíce", "začíná")
        substantiveTop = $true
    }
    "mohou mě propustit ve zkušební době" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("zkušební době", "zrušit pracovní poměr", "zaměstnavatel")
        substantiveTop = $true
    }
    "po 6 hodinách mám nárok na přestávku" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("přestávku", "6 hodin", "nejdéle po")
        substantiveTop = $true
    }
    "co dělat když mi zaměstnavatel nevyplatil mzdu" = @{
        expectedDoc = $ExpectedDoc
        requiredAny = @("nevyplatil mzdu", "15 dnů", "okamžitě zrušit")
        substantiveTop = $true
    }
}

$queries = @(
    # exact paragraf lookup
    "§ 34 zákoník práce",
    "§ 35 zákoník práce",
    "§ 39 zákoník práce",
    "§ 48 zákoník práce",
    "§ 50 zákoník práce",
    "§ 51 zákoník práce",
    "§ 52 zákoník práce",
    "§ 55 zákoník práce",
    "§ 56 zákoník práce",
    "§ 66 zákoník práce",
    "§ 67 zákoník práce",
    "§ 88 zákoník práce",
    "§ 96 zákoník práce",
    "§ 109 zákoník práce",
    "§ 111 zákoník práce",
    "§ 141 zákoník práce",
    "§ 211 zákoník práce",
    "§ 217 zákoník práce",
    "§ 222 zákoník práce",
    "zákon 262/2006 § 52",

    # law-constrained topic queries
    "výpovědní důvody zákoník práce",
    "výpovědní doba zákoník práce",
    "okamžité zrušení pracovního poměru zákoník práce",
    "odstupné zákoník práce podmínky",
    "dovolená zákoník práce délka",
    "pracovní smlouva zákoník práce náležitosti",
    "zkušební doba zákoník práce délka",
    "pracovní doba zákoník práce maximum",
    "přestávka v práci zákoník práce",
    "splatnost mzdy zákoník práce",
    "minimální mzda zákoník práce",
    "dohoda o provedení práce zákoník práce",
    "dohoda o pracovní činnosti zákoník práce",
    "práce přesčas zákoník práce",
    "noční práce zákoník práce",

    # natural-language labor questions
    "mám nárok na odstupné při nadbytečnosti",
    "kdy může zaměstnavatel dát výpověď",
    "jak dlouhá je výpovědní doba",
    "mohou mě propustit ve zkušební době",
    "po 6 hodinách mám nárok na přestávku",
    "co dělat když mi zaměstnavatel nevyplatil mzdu",
    "kolik dovolené mám za rok",
    "může mi zaměstnavatel nařídit přesčas",
    "může být pracovní smlouva na dobu určitou opakovaně",
    "kdy dostanu mzdu po skončení měsíce",
    "může zaměstnavatel okamžitě zrušit pracovní poměr",
    "musí být pracovní smlouva písemná",
    "můžu se vzdát nároku na mzdu",
    "mohu si převést nevyčerpanou dovolenou",
    "kdy může zaměstnanec okamžitě zrušit pracovní poměr"
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
        $answerText  = ("$summary`n$explanation").ToLower()

        if (-not (Test-DocMatch -DocId $docIds -Expected $ExpectedDoc)) {
            $status = "FAIL"
            $detail = "expected doc $ExpectedDoc, got $docIds"
        }

        if ($status -eq "PASS" -and $rules.ContainsKey($q)) {
            $rule = $rules[$q]

            if ($rule.ContainsKey("substantiveTop") -and $rule["substantiveTop"] -and (Test-IsStructuralText -Text ($topResult.text))) {
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

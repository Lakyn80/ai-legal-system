import type { CaseDocument, CaseTreeNode, AnalysisOutput } from "./types";

export const caseDocuments: CaseDocument[] = [
  {
    id: "doc-1",
    title: "Rozsudek okresního soudu",
    type: "judgment",
    date: "2024-03-15",
    pageCount: 6,
    content: [
      "ROZSUDEK\nJMÉNEM REPUBLIKY\n\nOkresní soud v Uherském Hradišti rozhodl samosoudcem JUDr. Janem Novákem ve věci žalobce: Městský úřad Polešovice, IČO: 00291234, se sídlem Náměstí 15, 687 37 Polešovice, proti žalovanému: PVM Deal s.r.o., IČO: 12345678, se sídlem Průmyslová 42, 687 37 Polešovice, zastoupenému advokátem Mgr. Petrem Dvořákem, o zaplacení částky 485.000 Kč s příslušenstvím,",
      "takto:\n\nI. Žalovaný je povinen zaplatit žalobci částku 485.000 Kč (slovy: čtyři sta osmdesát pět tisíc korun českých) spolu s úrokem z prodlení ve výši 8,25 % ročně z této částky od 1. 6. 2023 do zaplacení, a to do 15 dnů od právní moci tohoto rozsudku.\n\nII. Žalovaný je povinen zaplatit žalobci na náhradě nákladů řízení částku 58.200 Kč, a to do 15 dnů od právní moci tohoto rozsudku k rukám právního zástupce žalobce.",
      "Odůvodnění:\n\nŽalobce se žalobou podanou dne 15. 9. 2023 domáhal po žalovaném zaplacení částky 485.000 Kč s příslušenstvím z titulu náhrady škody způsobené porušením smluvních povinností dle Smlouvy o dílo č. 2022/456 ze dne 1. 3. 2022.\n\nŽalobce tvrdil, že žalovaný nedodržel termín dokončení díla stanovený na 30. 4. 2023 a dílo nebylo dokončeno ani ke dni podání žaloby. V důsledku prodlení žalovaného vznikla žalobci škoda sestávající z nákladů na zajištění náhradního plnění a ušlého zisku.",
      "Soud provedl dokazování listinnými důkazy – Smlouvou o dílo č. 2022/456, fakturami č. 2023001 až 2023012, znaleckým posudkem Ing. Karla Svobody č. 45/2023, výslechem svědků Ing. Marka Procházky a Jany Veselé.\n\nZ provedených důkazů soud zjistil, že žalovaný skutečně porušil smluvní povinnost dokončit dílo v dohodnutém termínu. Znaleckým posudkem bylo prokázáno, že škoda způsobená žalobci činí nejméně 485.000 Kč.",
      "Soud se zabýval námitkou žalovaného, že prodlení bylo způsobeno nepředvídatelnými okolnostmi – konkrétně změnou legislativních požadavků na zpracování odpadů platnou od 1. 1. 2023. Tuto námitku soud neshledal důvodnou, neboť žalovaný jako odborník v oboru měl a mohl předpokládat možnost legislativních změn a měl v rámci řádné péče zahrnout toto riziko do svého plánu plnění.\n\nSoud dále konstatoval, že žalovaný neprokázal existenci vyšší moci ve smyslu § 2913 odst. 2 občanského zákoníku.",
      "S ohledem na výše uvedené skutečnosti soud žalobě v plném rozsahu vyhověl.\n\nO náhradě nákladů řízení bylo rozhodnuto podle § 142 odst. 1 o. s. ř.\n\nPoučení: Proti tomuto rozsudku lze podat odvolání do 15 dnů ode dne doručení jeho písemného vyhotovení ke Krajskému soudu v Brně prostřednictvím Okresního soudu v Uherském Hradišti.\n\nV Uherském Hradišti dne 15. března 2024\nJUDr. Jan Novák v. r.\nsamosoudce",
    ],
    metadata: {
      court: "Okresní soud v Uherském Hradišti",
      judge: "JUDr. Jan Novák",
      caseNumber: "12 C 45/2023",
      parties: "Městský úřad Polešovice vs. PVM Deal s.r.o.",
      filed: "2023-09-15",
    },
  },
  {
    id: "doc-2",
    title: "Odvolání proti rozsudku",
    type: "appeal",
    date: "2024-04-02",
    pageCount: 4,
    content: [
      "ODVOLÁNÍ\n\nKrajskému soudu v Brně\nprostřednictvím Okresního soudu v Uherském Hradišti\n\nVěc: 12 C 45/2023\nOdvolatel: PVM Deal s.r.o., IČO: 12345678\nZastoupen: Mgr. Petr Dvořák, advokát\n\nOdvolatel tímto podává v zákonné lhůtě odvolání proti rozsudku Okresního soudu v Uherském Hradišti ze dne 15. 3. 2024.",
      "Důvody odvolání:\n\n1. Nesprávné právní posouzení věci\n\nSoud prvního stupně nesprávně posoudil otázku příčinné souvislosti mezi údajným porušením smluvní povinnosti žalovaného a vzniklou škodou. Žalovaný namítá, že prodlení bylo způsobeno výlučně změnou legislativních požadavků, které nebylo možné předvídat.\n\n2. Nesprávné skutkové zjištění\n\nSoud se nedostatečně vypořádal s důkazy předloženými žalovaným, zejména s odborným vyjádřením Ing. Tomáše Krejčího ze dne 10. 1. 2024.",
      "3. Nepřiměřenost přiznané částky\n\nI v případě, že by soud shledal odpovědnost žalovaného za prodlení, přiznaná částka 485.000 Kč je nepřiměřeně vysoká. Žalobce neprokázal, že náklady na zajištění náhradního plnění skutečně dosáhly tvrzené výše.\n\n4. Procesní vady\n\nSoud prvního stupně zamítl návrh žalovaného na provedení revizního znaleckého posudku, čímž porušil právo žalovaného na spravedlivý proces.",
      "Petit:\n\nS ohledem na výše uvedené odvolatel navrhuje, aby odvolací soud:\n\na) napadený rozsudek změnil tak, že žalobu v plném rozsahu zamítne, nebo\nb) napadený rozsudek zrušil a věc vrátil soudu prvního stupně k dalšímu řízení.\n\nV Uherském Hradišti dne 2. dubna 2024\n\nMgr. Petr Dvořák v. r.\nadvokát",
    ],
    metadata: {
      court: "Krajský soud v Brně",
      caseNumber: "12 C 45/2023",
      parties: "PVM Deal s.r.o. (odvolatel)",
      filed: "2024-04-02",
    },
  },
  {
    id: "doc-3",
    title: "Znalecký posudek – výše škody",
    type: "evidence",
    date: "2023-12-01",
    pageCount: 3,
    content: [
      "ZNALECKÝ POSUDEK č. 45/2023\n\nZnalec: Ing. Karel Svoboda, Ph.D.\nObor: Ekonomika – oceňování škod a ztrát\nJmenován: rozhodnutím Krajského soudu v Brně ze dne 15. 10. 2023\n\nÚkol: Stanovit výši škody vzniklé Městskému úřadu Polešovice v důsledku prodlení s dokončením díla dle Smlouvy o dílo č. 2022/456.",
      "Posouzení:\n\nNa základě analýzy předložených podkladů jsem stanovil výši škody následovně:\n\n1. Náklady na zajištění náhradního plnění:\n   - Demontáž nedokončeného díla: 85.000 Kč\n   - Výběrové řízení na náhradního dodavatele: 15.000 Kč\n   - Realizace náhradním dodavatelem (rozdíl cen): 210.000 Kč\n   Celkem: 310.000 Kč\n\n2. Ušlý zisk:\n   - Období prostoje: 5 měsíců\n   - Průměrný měsíční výnos z provozu: 35.000 Kč\n   Celkem: 175.000 Kč\n\nCelková škoda: 485.000 Kč",
      "Závěr:\n\nCelková škoda vzniklá žalobci v důsledku prodlení žalovaného s dokončením díla činí 485.000 Kč.\n\nTato částka zahrnuje jak skutečnou škodu ve výši 310.000 Kč, tak ušlý zisk ve výši 175.000 Kč.\n\nV Brně dne 1. prosince 2023\n\nIng. Karel Svoboda, Ph.D. v. r.\nznalec",
    ],
    metadata: {
      caseNumber: "12 C 45/2023",
    },
  },
  {
    id: "doc-4",
    title: "Smlouva o dílo č. 2022/456",
    type: "contract",
    date: "2022-03-01",
    pageCount: 5,
    content: [
      "SMLOUVA O DÍLO č. 2022/456\n\nuzavřená dle § 2586 a násl. zákona č. 89/2012 Sb., občanský zákoník\n\nSmluvní strany:\n\nObjednatel: Městský úřad Polešovice, IČO: 00291234\nZhotovitel: PVM Deal s.r.o., IČO: 12345678",
      "Článek I. – Předmět smlouvy\n\n1.1 Zhotovitel se zavazuje provést kompletní rekonstrukci systému třídění a zpracování odpadů v areálu objednatele.\n\n1.2 Dílo zahrnuje demontáž stávajícího systému, dodávku a montáž nové třídící linky, instalaci automatizovaného řídícího systému, zkušební provoz a zaškolení obsluhy.",
      "Článek II. – Cena díla\n\n2.1 Cena díla činí 2.850.000 Kč bez DPH.\n2.2 Cena je stanovena jako cena nejvýše přípustná.\n\nČlánek III. – Termín plnění\n\n3.1 Dílo bude dokončeno a předáno nejpozději do 30. 4. 2023.\n3.2 Za prodlení je zhotovitel povinen zaplatit smluvní pokutu ve výši 0,05 % z ceny díla za každý den prodlení.",
      "Článek IV. – Práva a povinnosti\n\n4.1 Zhotovitel je povinen provést dílo s odbornou péčí v souladu s platnými technickými normami.\n4.2 Objednatel je povinen poskytnout nezbytnou součinnost.",
      "Článek VII. – Závěrečná ustanovení\n\n7.1 Tato smlouva nabývá účinnosti dnem podpisu oběma smluvními stranami.\n\nV Polešovicích dne 1. března 2022\n\nZa objednatele: Ing. Marek Procházka v. r.\nZa zhotovitele: Pavel Matoušek v. r.",
    ],
    metadata: {
      parties: "Městský úřad Polešovice × PVM Deal s.r.o.",
      filed: "2022-03-01",
    },
  },
  {
    id: "doc-5",
    title: "Vyjádření k žalobě",
    type: "objection",
    date: "2023-11-10",
    pageCount: 3,
    content: [
      "VYJÁDŘENÍ K ŽALOBĚ\n\nOkresnímu soudu v Uherském Hradišti\n\nVěc: 12 C 45/2023\nŽalovaný: PVM Deal s.r.o.\nZastoupen: Mgr. Petr Dvořák, advokát\n\nŽalovaný navrhuje, aby soud žalobu v plném rozsahu zamítl.",
      "1. K tvrzení o porušení smluvní povinnosti\n\nŽalovaný uznává, že dílo nebylo dokončeno v termínu. Důvodem prodlení však nebyla nedbalost žalovaného, nýbrž zásadní změna legislativního prostředí – novela zákona o odpadech účinná od 1. 1. 2023. Tato okolnost představuje překážku ve smyslu § 2913 odst. 2 občanského zákoníku.",
      "3. Důkazní návrhy\n\nŽalovaný navrhuje provedení:\na) Odborné vyjádření Ing. Tomáše Krejčího\nb) Komunikace mezi smluvními stranami z 1–4/2023\nc) Revizní znalecký posudek k výši škody\n\nV Uherském Hradišti dne 10. listopadu 2023\n\nMgr. Petr Dvořák v. r.\nadvokát",
    ],
    metadata: {
      court: "Okresní soud v Uherském Hradišti",
      caseNumber: "12 C 45/2023",
      filed: "2023-11-10",
    },
  },
  {
    id: "doc-6",
    title: "Usnesení o nařízení jednání",
    type: "order",
    date: "2023-12-15",
    pageCount: 1,
    content: [
      "USNESENÍ\n\nOkresní soud v Uherském Hradišti\nč. j. 12 C 45/2023-52\n\nNařizuje se jednání na den 15. února 2024 v 9:00 hodin v jednací síni č. 3.\n\nÚčastníci řízení jsou povinni se k jednání dostavit osobně nebo prostřednictvím svého zástupce.\n\nV Uherském Hradišti dne 15. prosince 2023\nJUDr. Jan Novák v. r.",
    ],
    metadata: {
      court: "Okresní soud v Uherském Hradišti",
      judge: "JUDr. Jan Novák",
      caseNumber: "12 C 45/2023",
    },
  },
];

export const caseTree: CaseTreeNode[] = [
  {
    id: "root",
    label: "Spis 12 C 45/2023",
    children: [
      {
        id: "full-case",
        label: "Celý spis",
        documentId: "__full_case__",
      },
      {
        id: "court-decisions",
        label: "Rozhodnutí soudu",
        children: [
          { id: "t-1", label: "Rozsudek okresního soudu", documentId: "doc-1" },
          { id: "t-6", label: "Usnesení o nařízení jednání", documentId: "doc-6" },
        ],
      },
      {
        id: "appeals",
        label: "Odvolání",
        children: [
          { id: "t-2", label: "Odvolání proti rozsudku", documentId: "doc-2" },
        ],
      },
      {
        id: "contracts",
        label: "Smlouvy",
        children: [
          { id: "t-4", label: "Smlouva o dílo č. 2022/456", documentId: "doc-4" },
        ],
      },
      {
        id: "evidence",
        label: "Důkazy",
        children: [
          { id: "t-3", label: "Znalecký posudek – výše škody", documentId: "doc-3" },
        ],
      },
      {
        id: "objections",
        label: "Námitky / Obrana",
        children: [
          { id: "t-5", label: "Vyjádření k žalobě", documentId: "doc-5" },
        ],
      },
    ],
  },
];

export const documentTypeLabels: Record<string, string> = {
  judgment: "Rozsudek",
  appeal: "Odvolání",
  petition: "Návrh",
  evidence: "Důkaz",
  objection: "Námitka",
  motion: "Návrh",
  order: "Usnesení",
  testimony: "Výpověď",
  contract: "Smlouva",
  correspondence: "Korespondence",
};

export const mockAnalysisOutput: AnalysisOutput = {
  runId: "mock-run-id",
  caseId: "mock-case-id",
  issueSummary:
    "Spor o náhradu škody 485.000 Kč za prodlení se zhotovením díla (rekonstrukce třídící linky). Klíčová otázka: zda novelizace zákona o odpadech (1. 1. 2023) představuje liberační důvod dle § 2913 odst. 2 OZ.",
  legalOptions: [
    "Podat kasační stížnost k Nejvyššímu soudu – namítnutí nesprávného výkladu § 2913 odst. 2 OZ",
    "Navrhnout revizní znalecký posudek k přezkumu výše škody",
    "Zpochybnit procesní postup soudu – zamítnutí důkazního návrhu na revizní posudek",
    "Mediace – návrh na mimosoudní narovnání s redukcí pohledávky",
  ],
  applicableLaws: [
    "§ 2913 odst. 2 OZ – liberační důvod (překážka mimo sféru dlužníka)",
    "§ 2894 OZ – předpoklady odpovědnosti za škodu",
    "§ 142 odst. 1 o. s. ř. – náhrada nákladů řízení",
    "Zákon č. 541/2020 Sb. – zákon o odpadech (novelizace platná od 1. 1. 2023)",
  ],
  risks: [
    "Nízká pravděpodobnost úspěchu kasace – soud prvního i druhého stupně posoudil věc shodně",
    "Náklady řízení mohou dále narůstat",
    "Exekuce může být zahájena při nesplnění rozsudku",
  ],
  nextSteps: [
    "Do 15 dnů od doručení rozsudku odvolacího soudu zvážit podání dovolání",
    "Zajistit odborné vyjádření k legislativní změně k. 1. 1. 2023",
    "Ověřit termín promlčení a procesní lhůty",
  ],
  defenseBlocks: [],
};

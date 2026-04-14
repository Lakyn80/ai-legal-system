"""
Focused Russian legal taxonomy for current retrieval scope only.

Scope (intentionally narrow):
- civil procedure issues around participation, notice, language, interpreter
- family-law alimony basis
- alimony-related enforcement support in currently ingested laws
- direct fair-trial support via ECHR art. 6

Out of scope by design:
- broad civil/property/tax/criminal/business mapping
- full-corpus Russian law coverage
- LLM classification
"""
from __future__ import annotations

from app.modules.common.legal_taxonomy.schemas import (
    ArticleTaxonomyItem,
    FocusTaxonomyDataset,
    LawTaxonomyItem,
)


RUSSIA_FOCUS_DATASET = FocusTaxonomyDataset(
    dataset_id="ru_focus_v1",
    jurisdiction="russia",
    scope_notes=(
        "Curated subset for interpreter/language/notice procedural issues and "
        "alimony + alimony enforcement support."
    ),
    laws=[
        LawTaxonomyItem(
            law_id="local:ru/gpk",
            law_short="ГПК РФ",
            law_full_name="Гражданский процессуальный кодекс Российской Федерации",
            broad_domain="civil_procedure",
            supported_primary_topics=[
                "language_of_proceedings",
                "interpreter_rights",
                "proper_notice_service",
                "procedural_participation",
                "appellate_reversal",
                "foreign_service_procedure",
                "recognition_enforcement",
            ],
            supported_secondary_topics=["alimony_procedure", "enforcement_procedure_support"],
            notes_for_retrieval=(
                "Primary procedural law for hearing participation defects "
                "(notice/service/language/interpreter)."
            ),
        ),
        LawTaxonomyItem(
            law_id="local:ru/sk",
            law_short="СК РФ",
            law_full_name="Семейный кодекс Российской Федерации",
            broad_domain="family_law",
            supported_primary_topics=["alimony", "alimony_debt", "alimony_obligation"],
            supported_secondary_topics=["alimony_enforcement_support"],
            notes_for_retrieval=(
                "Primary substantive basis for child-support obligations and debt-related claims."
            ),
        ),
        LawTaxonomyItem(
            law_id="local:ru/echr",
            law_short="ЕКПЧ",
            law_full_name="Конвенция о защите прав человека и основных свобод",
            broad_domain="human_rights_support",
            supported_primary_topics=[],
            supported_secondary_topics=["fair_trial_support", "language_access_support"],
            notes_for_retrieval=(
                "Supporting source only; not a substitute for GPK procedural anchors."
            ),
        ),
        LawTaxonomyItem(
            law_id="local:ru/fl115",
            law_short="ФЗ-115",
            law_full_name="О правовом положении иностранных граждан в Российской Федерации",
            broad_domain="foreign_status_support",
            supported_primary_topics=[],
            supported_secondary_topics=["foreign_party_status_support"],
            notes_for_retrieval=(
                "Supporting context for foreign-citizen procedural participation cases."
            ),
        ),
    ],
    articles=[
        # GPK anchors for active procedural cluster
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="9",
            article_heading="Язык гражданского судопроизводства",
            short_topic_label="language_of_proceedings",
            detailed_topic_labels=[
                "language_of_proceedings",
                "interpreter_rights",
                "procedural_participation",
            ],
            issue_flags=["language_issue", "interpreter_issue"],
            retrieval_keywords_ru=[
                "язык судопроизводства",
                "язык гражданского судопроизводства",
                "не владеет языком",
                "право на переводчика",
            ],
            retrieval_keywords_cz=[
                "jazyk soudního řízení",
                "neovládá jazyk řízení",
                "právo na tlumočníka",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Primary procedural anchor when party does not understand the language "
                "or needs interpreter support."
            ),
            exclude_for_topics=["alimony_property_division", "land_rights"],
            related_articles=["local:ru/gpk:162", "local:ru/echr:6"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="162",
            article_heading="Переводчик",
            short_topic_label="interpreter_rights",
            detailed_topic_labels=[
                "interpreter_rights",
                "translation_in_hearing",
                "procedural_participation",
            ],
            issue_flags=["interpreter_issue", "language_issue"],
            retrieval_keywords_ru=[
                "переводчик в гражданском процессе",
                "без переводчика",
                "не предоставили переводчика",
                "перевод документов",
            ],
            retrieval_keywords_cz=[
                "tlumočník v civilním řízení",
                "bez tlumočníka",
                "nebyl zajištěn překlad",
            ],
            anchor_priority="strong",
            legal_role="procedural_support",
            summary_for_retrieval=(
                "Secondary article for interpreter participation defects. "
                "Regulates the interpreter's role at hearing; the primary right is GPK 9."
            ),
            exclude_for_topics=["tax_enforcement", "commercial_arbitration"],
            related_articles=["local:ru/gpk:9", "local:ru/echr:6"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="113",
            article_heading="Судебные извещения и вызовы",
            short_topic_label="proper_notice_service",
            detailed_topic_labels=[
                "proper_notice_service",
                "summons",
                "service_of_process",
            ],
            issue_flags=["notice_issue"],
            retrieval_keywords_ru=[
                "извещение сторон",
                "судебная повестка",
                "не был уведомлен",
                "без извещения",
                "надлежащее извещение",
            ],
            retrieval_keywords_cz=[
                "řádné vyrozumění",
                "soudní předvolání",
                "bez oficiálního vyrozumění",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Core notice/summons anchor for claims that hearing proceeded without proper service."
            ),
            exclude_for_topics=["alimony_amount_calculation"],
            related_articles=["local:ru/gpk:116", "local:ru/gpk:167"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="116",
            article_heading="Вручение судебных извещений и вызовов",
            short_topic_label="service_mechanics",
            detailed_topic_labels=[
                "service_of_process",
                "delivery_rules",
                "actual_residence_service_context",
            ],
            issue_flags=["notice_issue", "service_address_issue"],
            retrieval_keywords_ru=[
                "вручение судебной повестки",
                "вручение извещения",
                "адрес вручения",
                "повестка не вручена",
            ],
            retrieval_keywords_cz=[
                "doručení předvolání",
                "adresa doručení",
                "předvolání nebylo doručeno",
            ],
            anchor_priority="strong",
            legal_role="procedural_support",
            summary_for_retrieval=(
                "Supports technical service/delivery defects, including contested address delivery."
            ),
            exclude_for_topics=["alimony_substance"],
            related_articles=["local:ru/gpk:113"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="167",
            article_heading="Последствия неявки лиц, участвующих в деле, в судебное заседание",
            short_topic_label="hearing_in_absence",
            detailed_topic_labels=[
                "procedural_participation",
                "hearing_in_absence",
                "notice_prerequisite",
            ],
            issue_flags=["notice_issue", "procedural_participation_issue"],
            retrieval_keywords_ru=[
                "рассмотрел дело в отсутствие",
                "неявка сторон",
                "рассмотрение без участия",
            ],
            retrieval_keywords_cz=[
                "řízení v nepřítomnosti",
                "projednáno bez účasti",
            ],
            anchor_priority="strong",
            legal_role="procedural_support",
            summary_for_retrieval=(
                "Supports argument that hearing in absence is improper when notice preconditions are not met."
            ),
            exclude_for_topics=["alimony_debt_calculation"],
            related_articles=["local:ru/gpk:113"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="117",
            article_heading="Надлежащее извещение",
            short_topic_label="proper_notice_definition",
            detailed_topic_labels=[
                "proper_notice_service",
                "service_of_process",
                "notice_validity",
            ],
            issue_flags=["notice_issue", "service_address_issue"],
            retrieval_keywords_ru=[
                "надлежащее извещение",
                "считается извещенным надлежащим образом",
                "доказательства получения извещения",
                "извещение получено адресатом",
            ],
            retrieval_keywords_cz=[
                "řádné vyrozumění",
                "považuje se za vyrozuměného",
                "důkaz o doručení",
            ],
            anchor_priority="strong",
            legal_role="procedural_support",
            summary_for_retrieval=(
                "Defines the legal standard for valid service. Central to disputing whether "
                "delivery to a foreign or wrong address satisfies the proper-notice requirement."
            ),
            exclude_for_topics=["alimony_substance"],
            related_articles=["local:ru/gpk:113", "local:ru/gpk:116"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="112",
            article_heading="Восстановление процессуальных сроков",
            short_topic_label="procedural_deadline_restoration",
            detailed_topic_labels=[
                "procedural_deadline_restoration",
                "procedural_participation",
                "proper_notice_service",
            ],
            issue_flags=["missed_deadline_due_to_service_issue"],
            retrieval_keywords_ru=[
                "восстановление процессуального срока",
                "пропущенный срок обжалования",
                "уважительная причина пропуска срока",
                "восстановить срок на подачу жалобы",
                "срок пропущен по уважительной причине",
            ],
            retrieval_keywords_cz=[
                "obnovení procesní lhůty",
                "zmeškání lhůty k odvolání",
                "omluvitelný důvod zmeškání lhůty",
                "obnovit lhůtu k odvolání",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Allows restoring missed procedural deadlines on showing a valid reason. "
                "Applicable when defendant missed the appellate deadline because they were "
                "not properly served with the judgment due to service defects."
            ),
            exclude_for_topics=["alimony_amount_calculation", "alimony_debt"],
            related_articles=["local:ru/gpk:113", "local:ru/gpk:330"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="330",
            article_heading="Основания для отмены или изменения решения суда в апелляционном порядке",
            short_topic_label="appellate_reversal",
            detailed_topic_labels=[
                "appellate_reversal",
                "mandatory_reversal_grounds",
                "procedural_participation",
            ],
            issue_flags=["appellate_reversal_issue"],
            retrieval_keywords_ru=[
                "основания для отмены решения суда",
                "безусловные основания отмены",
                "рассмотрение дела в отсутствие не извещенного лица",
                "нарушение правил о языке судопроизводства",
                "отмена апелляционным судом",
            ],
            retrieval_keywords_cz=[
                "důvody pro zrušení rozhodnutí soudu",
                "povinné zrušení rozhodnutí",
                "projednáno bez řádného uvyrozumění",
                "porušení jazykových pravidel řízení",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Primary appellate attack anchor. Part 4.2: mandatory reversal when party not properly "
                "notified and hearing proceeded in their absence. Part 4.3: mandatory reversal for "
                "language rule violations. Both directly match defendant's objections."
            ),
            exclude_for_topics=["alimony_amount_calculation", "alimony_debt"],
            related_articles=["local:ru/gpk:113", "local:ru/gpk:9", "local:ru/gpk:167"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="398",
            article_heading="Процессуальные права и обязанности иностранных лиц",
            short_topic_label="foreign_party_procedural_rights",
            detailed_topic_labels=[
                "foreign_party_procedural_rights",
                "procedural_participation",
                "foreign_service_procedure",
            ],
            issue_flags=["foreign_party_issue", "foreign_service_issue"],
            retrieval_keywords_ru=[
                "процессуальные права иностранных граждан",
                "иностранные лица в российском суде",
                "равные права иностранцев в процессе",
                "иностранное лицо участвует в деле",
            ],
            retrieval_keywords_cz=[
                "procesní práva cizinců v Rusku",
                "cizí státní příslušník v ruském soudním řízení",
                "rovná procesní práva",
            ],
            anchor_priority="strong",
            legal_role="procedural_support",
            summary_for_retrieval=(
                "Establishes equal procedural rights for foreign nationals. Supports argument that "
                "all notice, language and interpreter obligations apply equally to foreign-address defendants."
            ),
            exclude_for_topics=["alimony_debt_calculation"],
            related_articles=["local:ru/gpk:407", "local:ru/gpk:9"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="407",
            article_heading="Судебные поручения",
            short_topic_label="foreign_service_procedure",
            detailed_topic_labels=[
                "foreign_service_procedure",
                "international_judicial_assistance",
                "service_of_process",
            ],
            issue_flags=["foreign_service_issue"],
            retrieval_keywords_ru=[
                "судебные поручения иностранным судам",
                "вручение извещений за рубежом",
                "поручение иностранному суду о вручении",
                "международный договор о правовой помощи",
                "доставка документов за границу",
            ],
            retrieval_keywords_cz=[
                "mezinárodní doručování",
                "doručení do zahraničí",
                "dožádání cizího soudu",
                "právní pomoc do zahraničí",
                "doručení v České republice",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Primary anchor for treaty-based international service of process. "
                "Applicable when defendant has foreign (e.g. Czech) address and should have been "
                "served through official judicial assistance channels."
            ),
            exclude_for_topics=["alimony_amount_calculation", "alimony_debt"],
            related_articles=["local:ru/gpk:113", "local:ru/gpk:398"],
        ),
        # GPK anchors for recognition and enforcement of foreign court decisions (Глава 45)
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="409",
            article_heading="Признание и исполнение решений иностранных судов",
            short_topic_label="recognition_enforcement",
            detailed_topic_labels=[
                "recognition_enforcement",
                "foreign_judgment_recognition",
                "international_treaty_basis",
            ],
            issue_flags=["recognition_enforcement_issue"],
            retrieval_keywords_ru=[
                "признание решений иностранных судов",
                "исполнение решения иностранного суда",
                "международный договор о признании",
                "принудительное исполнение иностранного решения",
                "решение иностранного суда в России",
            ],
            retrieval_keywords_cz=[
                "uznání rozhodnutí cizích soudů",
                "výkon rozhodnutí cizího soudu",
                "mezinárodní smlouva o uznání",
                "nucený výkon cizího rozhodnutí",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Primary anchor for recognition and enforcement of foreign court decisions in Russia. "
                "Requires international treaty basis. Sets 3-year enforcement deadline (restorable via "
                "ст. 112). Central for Czech-Russia bilateral recognition scenarios."
            ),
            exclude_for_topics=["alimony_amount_calculation", "alimony_debt"],
            related_articles=["local:ru/gpk:410", "local:ru/gpk:412", "local:ru/gpk:112"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="410",
            article_heading="Ходатайство о принудительном исполнении решения иностранного суда",
            short_topic_label="recognition_enforcement",
            detailed_topic_labels=[
                "recognition_enforcement",
                "enforcement_petition",
                "jurisdiction_for_petition",
            ],
            issue_flags=["recognition_enforcement_issue"],
            retrieval_keywords_ru=[
                "ходатайство о принудительном исполнении иностранного решения",
                "подача ходатайства в суд",
                "суд по месту жительства должника",
                "должник в Российской Федерации",
            ],
            retrieval_keywords_cz=[
                "žádost o nucený výkon cizího rozhodnutí",
                "příslušný soud pro exekuci",
                "místo bydliště dlužníka v Rusku",
            ],
            anchor_priority="strong",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Procedural anchor: governs where and how to file petition for enforcement of "
                "foreign judgment. Filed at regional court at debtor's Russian residence or "
                "asset location when debtor's address in Russia is unknown."
            ),
            exclude_for_topics=["alimony_amount_calculation", "alimony_debt"],
            related_articles=["local:ru/gpk:409", "local:ru/gpk:411", "local:ru/gpk:412"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="411",
            article_heading="Содержание ходатайства о принудительном исполнении решения иностранного суда",
            short_topic_label="recognition_enforcement",
            detailed_topic_labels=[
                "recognition_enforcement",
                "petition_requirements",
                "notice_in_foreign_proceedings",
            ],
            issue_flags=["recognition_enforcement_issue"],
            retrieval_keywords_ru=[
                "содержание ходатайства об исполнении",
                "документы для исполнения иностранного решения",
                "извещение стороны в иностранном процессе",
                "надлежащее уведомление в иностранном суде",
                "заверенный перевод решения",
            ],
            retrieval_keywords_cz=[
                "obsah žádosti o exekuci",
                "doklady k uznání cizího rozhodnutí",
                "vyrozumění strany v cizím řízení",
                "ověřený překlad rozhodnutí",
            ],
            anchor_priority="strong",
            legal_role="procedural_support",
            summary_for_retrieval=(
                "Specifies required content and documents for the enforcement petition. "
                "Part 2.4: must include proof that the party against whom the decision was taken "
                "was timely and properly notified about the foreign proceedings — directly links "
                "notice defect defenses to the documentary requirements."
            ),
            exclude_for_topics=["alimony_amount_calculation", "alimony_debt"],
            related_articles=["local:ru/gpk:409", "local:ru/gpk:410", "local:ru/gpk:412"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/gpk",
            article_num="412",
            article_heading="Отказ в принудительном исполнении решения иностранного суда",
            short_topic_label="recognition_enforcement_refusal",
            detailed_topic_labels=[
                "recognition_enforcement",
                "foreign_judgment_refusal_grounds",
                "notice_in_foreign_proceedings",
            ],
            issue_flags=["recognition_enforcement_issue"],
            retrieval_keywords_ru=[
                "отказ в принудительном исполнении",
                "основания отказа в признании иностранного решения",
                "не была извещена о времени и месте рассмотрения дела",
                "лишена возможности принять участие в процессе",
                "нарушение публичного порядка",
                "исключительная подсудность российских судов",
            ],
            retrieval_keywords_cz=[
                "odmítnutí výkonu cizího rozhodnutí",
                "důvody pro odmítnutí uznání",
                "nebyla vyrozuměna o řízení",
                "zbavena možnosti účasti v řízení",
                "rozpor s veřejným pořádkem",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Primary defense anchor: court must refuse enforcement if the party against whom "
                "the decision was taken was deprived of participation because they were not timely "
                "and properly notified (п.2 ч.1). Directly links notice defects in original foreign "
                "proceedings to mandatory refusal grounds in Russia."
            ),
            exclude_for_topics=["alimony_amount_calculation", "alimony_debt"],
            related_articles=["local:ru/gpk:409", "local:ru/gpk:411"],
        ),
        # Family code alimony anchors
        ArticleTaxonomyItem(
            law_id="local:ru/sk",
            article_num="80",
            article_heading="Обязанности родителей по содержанию несовершеннолетних детей",
            short_topic_label="alimony_obligation",
            detailed_topic_labels=["alimony", "child_support_obligation"],
            issue_flags=["alimony_issue"],
            retrieval_keywords_ru=[
                "обязанность содержать ребенка",
                "алименты на несовершеннолетних",
                "содержание детей",
            ],
            retrieval_keywords_cz=[
                "vyživovací povinnost rodičů",
                "výživné na nezletilé dítě",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Primary substantive anchor for existence of alimony obligation."
            ),
            exclude_for_topics=["notice_issue", "interpreter_issue"],
            related_articles=["local:ru/sk:81", "local:ru/sk:83"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/sk",
            article_num="81",
            article_heading="Размер алиментов, взыскиваемых на несовершеннолетних детей в судебном порядке",
            short_topic_label="alimony_amount",
            detailed_topic_labels=["alimony", "alimony_amount", "alimony_shares"],
            issue_flags=["alimony_issue", "alimony_calculation_issue"],
            retrieval_keywords_ru=[
                "размер алиментов",
                "доля от дохода",
                "взыскание алиментов",
            ],
            retrieval_keywords_cz=[
                "výše výživného",
                "podíl z příjmu",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Core for standard court-ordered alimony amount determination."
            ),
            exclude_for_topics=["language_issue", "notice_issue"],
            related_articles=["local:ru/sk:80", "local:ru/sk:83"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/sk",
            article_num="83",
            article_heading="Взыскание алиментов на несовершеннолетних детей в твердой денежной сумме",
            short_topic_label="alimony_fixed_amount",
            detailed_topic_labels=["alimony", "alimony_amount", "fixed_sum_alimony"],
            issue_flags=["alimony_issue", "alimony_calculation_issue"],
            retrieval_keywords_ru=[
                "твердая денежная сумма алиментов",
                "фиксированные алименты",
                "взыскание в твердой сумме",
            ],
            retrieval_keywords_cz=[
                "pevně stanovené výživné",
                "výživné pevnou částkou",
            ],
            anchor_priority="strong",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Strong alternative basis when fixed-sum alimony is sought instead of income share."
            ),
            exclude_for_topics=["service_address_issue"],
            related_articles=["local:ru/sk:81"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/sk",
            article_num="107",
            article_heading="Сроки обращения за алиментами",
            short_topic_label="alimony_time_scope",
            detailed_topic_labels=["alimony", "temporal_scope", "retroactive_limits"],
            issue_flags=["alimony_debt_issue"],
            retrieval_keywords_ru=[
                "срок обращения за алиментами",
                "прошедший период алименты",
                "за прошлое время",
            ],
            retrieval_keywords_cz=[
                "lhůta pro výživné",
                "výživné za minulou dobu",
            ],
            anchor_priority="strong",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Helps frame claim period and retroactive boundaries in alimony disputes."
            ),
            exclude_for_topics=["interpreter_issue"],
            related_articles=["local:ru/sk:113"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/sk",
            article_num="114",
            article_heading="Освобождение от уплаты задолженности по алиментам",
            short_topic_label="alimony_debt_exemption",
            detailed_topic_labels=["alimony_debt", "alimony_debt_exemption", "valid_reason_defense"],
            issue_flags=["alimony_exemption_issue", "alimony_debt_issue"],
            retrieval_keywords_ru=[
                "освобождение от задолженности по алиментам",
                "уважительные причины неуплаты алиментов",
                "болезнь и неуплата алиментов",
                "суд освобождает от уплаты долга по алиментам",
                "не мог платить алименты по уважительным причинам",
            ],
            retrieval_keywords_cz=[
                "prominutí dluhu na výživném",
                "omluvitelné důvody neplacení výživného",
                "osvobození od nedoplatku výživného",
                "nemohl platit výživné",
            ],
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Key defense anchor: court may exempt debtor fully or partially from alimony arrears "
                "when non-payment was due to valid reason (illness or other omluvitelné důvody). "
                "Directly applicable when defendant claims non-payment resulted from improper notice "
                "and inability to participate in proceedings."
            ),
            exclude_for_topics=["alimony_obligation_existence"],
            related_articles=["local:ru/sk:113", "local:ru/sk:115"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/sk",
            article_num="113",
            article_heading="Определение задолженности по алиментам",
            short_topic_label="alimony_debt",
            detailed_topic_labels=["alimony_debt", "debt_calculation", "enforcement_support"],
            issue_flags=["alimony_debt_issue", "alimony_enforcement_issue"],
            retrieval_keywords_ru=[
                "задолженность по алиментам",
                "определение задолженности",
                "расчет долга по алиментам",
            ],
            retrieval_keywords_cz=[
                "dluh na výživném",
                "výpočet dluhu výživného",
            ],
            anchor_priority="core",
            legal_role="enforcement_support",
            summary_for_retrieval=(
                "Core debt-calculation anchor for alimony arrears and enforcement-related disputes."
            ),
            exclude_for_topics=["property_land_dispute"],
            related_articles=["local:ru/sk:115", "local:ru/sk:117"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/sk",
            article_num="115",
            article_heading="Ответственность за несвоевременную уплату алиментов",
            short_topic_label="late_payment_liability",
            detailed_topic_labels=["alimony_debt", "liability", "enforcement_support"],
            issue_flags=["alimony_debt_issue", "alimony_enforcement_issue"],
            retrieval_keywords_ru=[
                "ответственность за неуплату алиментов",
                "неустойка по алиментам",
                "просрочка алиментов",
            ],
            retrieval_keywords_cz=[
                "odpovědnost za neplacení výživného",
                "sankce za prodlení výživného",
            ],
            anchor_priority="strong",
            legal_role="enforcement_support",
            summary_for_retrieval=(
                "Supports penalty/liability claims when alimony is paid late or not paid."
            ),
            exclude_for_topics=["notice_issue"],
            related_articles=["local:ru/sk:113"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/sk",
            article_num="117",
            article_heading="Индексация алиментов",
            short_topic_label="alimony_indexation",
            detailed_topic_labels=["alimony", "alimony_debt", "indexation"],
            issue_flags=["alimony_debt_issue"],
            retrieval_keywords_ru=[
                "индексация алиментов",
                "перерасчет алиментов",
                "увеличение алиментов по индексации",
            ],
            retrieval_keywords_cz=[
                "indexace výživného",
                "přepočet výživného",
            ],
            anchor_priority="secondary",
            legal_role="enforcement_support",
            summary_for_retrieval=(
                "Useful for debt amount adjustments and inflation/indexation context."
            ),
            exclude_for_topics=["interpreter_issue", "procedural_participation", "appellate_reversal"],
            related_articles=["local:ru/sk:113"],
        ),
        # Supporting sources for current procedural cluster
        ArticleTaxonomyItem(
            law_id="local:ru/echr",
            article_num="6",
            article_heading="Право на справедливое судебное разбирательство",
            short_topic_label="fair_trial_support",
            detailed_topic_labels=["fair_trial_support", "procedural_fairness_support"],
            issue_flags=["language_issue", "interpreter_issue", "notice_issue"],
            retrieval_keywords_ru=[
                "справедливое судебное разбирательство",
                "право на справедливый суд",
                "статья 6 екпч",
            ],
            retrieval_keywords_cz=[
                "spravedlivý proces",
                "článek 6 úmluvy",
            ],
            anchor_priority="strong",
            legal_role="supporting_basis",
            summary_for_retrieval=(
                "Supporting fair-trial frame for procedural defects; subordinate to GPK anchors."
            ),
            exclude_for_topics=["alimony_amount_only"],
            related_articles=["local:ru/gpk:9", "local:ru/gpk:113", "local:ru/gpk:162"],
        ),
        ArticleTaxonomyItem(
            law_id="local:ru/fl115",
            article_num="(topic)",
            article_heading="Правовое положение иностранных граждан (поддерживающий слой)",
            short_topic_label="foreign_party_status_support",
            detailed_topic_labels=["foreign_party_status_support", "procedural_participation_support"],
            issue_flags=["foreign_party_issue", "interpreter_issue"],
            retrieval_keywords_ru=[
                "правовое положение иностранных граждан",
                "иностранный гражданин в суде",
                "115-фз",
            ],
            retrieval_keywords_cz=[
                "právní postavení cizince",
                "cizinec u soudu",
            ],
            anchor_priority="secondary",
            legal_role="supporting_basis",
            summary_for_retrieval=(
                "Supporting layer for foreign-citizen status context when procedural participation is disputed."
            ),
            exclude_for_topics=["alimony_amount_calculation"],
            related_articles=["local:ru/gpk:9", "local:ru/gpk:162"],
        ),
    ],
)

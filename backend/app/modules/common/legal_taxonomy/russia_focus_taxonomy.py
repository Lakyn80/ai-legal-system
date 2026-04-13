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
            anchor_priority="core",
            legal_role="primary_basis",
            summary_for_retrieval=(
                "Primary article for interpreter participation defects and translation access."
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
            exclude_for_topics=["interpreter_issue"],
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

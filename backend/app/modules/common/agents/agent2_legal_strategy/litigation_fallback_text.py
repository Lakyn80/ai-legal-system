"""
Deterministic, evidence-grounded litigation copy for Agent 2 fallback when the LLM returns empty or shallow output.

Texts are written as senior-trial style FACT → RULE → VIOLATION → CONSEQUENCE chains.
Article numbers are keys; law labels come from the evidence pack at call site.
"""
from __future__ import annotations

# Primary basis: why_it_matters — multi-sentence causal chains (English; Russian cases often use English facts in tests).
PRIMARY_WHY_BY_ARTICLE: dict[str, str] = {
    "9": (
        "The facts describe a party who does not participate in Russian as a first language and proceedings "
        "conducted without adequate language safeguards. "
        "Article 9 ГПК РФ establishes the language of civil proceedings and the duty to secure the right "
        "to give explanations and receive translation where the party does not command the language of the court. "
        "Where that guarantee was not observed in substance, the party's right to participate meaningfully "
        "and to understand the record is compromised, which constitutes a procedural defect in the conduct of "
        "the hearing. "
        "That defect is not cosmetic: it goes to the fairness of the process and may form part of the basis "
        "for challenging the judgment and seeking appellate or cassation relief together with the other "
        "procedural violations in the file."
    ),
    "162": (
        "The case facts refer to proceedings without an interpreter or with inadequate interpreter participation. "
        "Article 162 ГПК РФ governs the interpreter's duties and the court's duty to instruct the interpreter "
        "and secure translation of testimony and documents for parties who do not command the language of "
        "proceedings. "
        "Failure to secure a qualified interpreter where one was required means the party could not adequately "
        "follow and respond — a direct impairment of defense rights in the hearing. "
        "This supports an argument that the hearing was not conducted in a manner that respected the party's "
        "procedural position, and may constitute grounds to revisit the lawfulness of the resulting judgment "
        "in combination with Articles 9 and 167 and the appellate grounds in Article 330."
    ),
    "113": (
        "Notice and summons are at the center of this file: the party alleges lack of proper notification, "
        "including in a cross-border context. "
        "Article 113 ГПК РФ regulates judicial notices and summons and the forms and channels by which parties "
        "are brought into the process. "
        "If notices were not directed or delivered in compliance with these rules relative to the party's "
        "actual address or foreign address, service may be defective. "
        "Defective service undermines the premise that the court had a properly informed adversarial process "
        "and may render absentee disposition problematic. "
        "This ties directly to reversal, reopening, or appellate attack vectors depending on posture and timing."
    ),
    "116": (
        "Physical delivery of the summons matters when the dispute is whether the addressee was reached at the "
        "correct place. "
        "Article 116 ГПК РФ addresses how a judicial summons is handed to a citizen or organization. "
        "If service was attempted only at a registration address where the party did not in fact reside, or "
        "without compliance with hand-delivery rules, the court's finding that the party was 'notified' may "
        "rest on an inadequate factual basis. "
        "That failure can constitute improper service rather than mere irregularity. "
        "The consequence is that proceeding to judgment in the party's absence may lack a valid procedural "
        "foundation for default or absentee review under Article 167."
    ),
    "167": (
        "Where the court proceeded without the party's participation, the conditions for absentee disposition "
        "must be legally satisfied. "
        "Article 167 ГПК РФ governs consequences of non-appearance, including when the court may proceed and "
        "when hearing must be postponed if notification is not established. "
        "If the party was not properly notified, treating the case as duly heard in absentia risks a judgment "
        "without genuine adversarial process. "
        "That is a structural procedural defect: it goes to the validity of the disposition, not to weight of "
        "evidence alone. "
        "It supports seeking cancellation, reversal, or reopening depending on the procedural stage and the "
        "grounds available under Article 330."
    ),
    "112": (
        "The party seeks restoration of a missed appellate or review deadline tied to lack of notice or late "
        "discovery of the judgment. "
        "Article 112 ГПК РФ allows restoration of missed procedural deadlines for reasons recognized as "
        "valid by the court. "
        "If the delay arose because the party did not receive the judgment or summons through no fault consistent "
        "with proper service, the court may restore the deadline upon a substantiated application and proof. "
        "This is the direct procedural vehicle to regain access to appellate review after a service defect. "
        "Without this step, later attacks on the judgment may be time-barred even though the underlying notice "
        "defect remains."
    ),
    "330": (
        "Appellate reversal requires specific grounds tied to material or procedural error. "
        "Article 330 ГПК РФ sets grounds for cancellation or amendment of a first-instance judgment on appeal, "
        "including violations of procedural law that affected the outcome. "
        "Where the record supports improper notice, interpreter failure, or unlawful absentee disposition, "
        "those circumstances may fall within procedural-violation grounds for reversal. "
        "The task is to map each alleged defect to the corresponding paragraph-level ground and show how it "
        "prejudiced the party's rights or the correctness of the decision. "
        "This article is the bridge from procedural facts to appellate relief."
    ),
    "407": (
        "Service abroad or to a foreign address often requires international judicial cooperation, not domestic "
        "posting alone. "
        "Article 407 ГПК РФ concerns letters rogatory and execution of foreign court requests for procedural "
        "acts including service abroad under treaties and federal law. "
        "If the court purported to serve a party at a Czech address without following the applicable "
        "international-assistance route, the service chain may be legally incomplete. "
        "That constitutes a defect in how notice was effected across borders. "
        "The consequence is that any finding of proper notice may be challenged as not lawfully established, "
        "with downstream effects on absentee hearing and enforcement."
    ),
    "398": (
        "Foreign status does not waive procedural equality. "
        "Article 398 ГПК РФ affirms procedural rights and duties of foreign persons in Russian courts. "
        "It reinforces that foreign parties are entitled to the same procedural protections—including notice, "
        "language, and participation—as the code guarantees generally. "
        "Combined with Articles 9, 113, and 407, it supports the position that abbreviated or informal "
        "service to a foreign address without treaty-compliant channels is incompatible with equal protection "
        "of procedural rights in this case."
    ),
    "80": (
        "Substantively, the dispute concerns alimony for a minor child. "
        "Article 80 СК РФ establishes parents' duty to maintain minor children and the court's power to "
        "order support when parents fail to provide it. "
        "That norm supplies the material basis for any alimony award — but in this file the primary fight is "
        "whether the award was reached in a procedurally lawful hearing. "
        "Even if the duty exists in principle, a judgment procured without notice or interpreter may be "
        "vulnerable on procedural grounds before the court reaches the amount. "
        "Use Article 80 to frame the subject matter while routing invalidity arguments through procedural articles."
    ),
    "81": (
        "Article 81 СК РФ sets default judicial shares for child support when no agreement exists. "
        "It matters for quantum and for comparing the first-instance award to statutory ranges. "
        "If the judgment exceeded or misapplied these shares without a proper hearing, the amount analysis "
        "intersects with procedural defects: the court may not have had a fair record on income and expenses. "
        "Preserve a secondary line that, after procedural relief, the court should recalculate support in "
        "accordance with Article 81 and proven means."
    ),
}

SUPPORTING_HOW: dict[str, str] = {
    "398": (
        "Article 398 frames equal procedural standing for foreign persons and reinforces that the court must "
        "apply the full ГПК toolkit—notice, language, cross-border service—not informal shortcuts. "
        "It strengthens the primary anchors on Articles 9, 113, and 407 by showing that the defect is not "
        "merely tactical but inconsistent with the statutory position of foreign defendants in Russian "
        "proceedings."
    ),
    "6": (
        "Article 6 ECHR guarantees a fair hearing within a reasonable time and equality of arms in civil "
        "matters. "
        "It does not replace domestic procedural articles but supports the proposition that denial of "
        "interpretation, unknowable proceedings, and absentee judgment without real notice implicate fair-trial "
        "values. "
        "Use it as supplementary framing where the domestic pack already contains this provision; do not elevate "
        "it above ГПК primary grounds unless the fact pattern clearly supports it."
    ),
}


def detailed_issue_comment(issue: str, facts_preview: list[str]) -> str:
    """Multi-sentence FACT → RULE → VIOLATION → CONSEQUENCE per issue flag."""
    fact_bits = "; ".join(facts_preview) if facts_preview else "the facts on file"
    templates: dict[str, str] = {
        "language_issue": (
            f"Facts: {fact_bits}. "
            "Legal rule: Article 9 ГПК РФ secures language rights and translation. "
            "Violation: proceedings conducted without securing comprehension and response in a language the party "
            "commands. "
            "Consequence: impaired participation and a procedural defect that may support reversal or remand "
            "under Article 330 together with interpreter-related grounds."
        ),
        "interpreter_issue": (
            f"Facts: {fact_bits}. "
            "Legal rule: Articles 9 and 162 ГПК РФ require proper interpreter arrangements and translation. "
            "Violation: hearing proceeded without a qualified interpreter or without effective translation. "
            "Consequence: the record may not reflect a knowing waiver of rights; supports appellate challenge "
            "and may affect validity of absentee disposition under Article 167."
        ),
        "notice_issue": (
            f"Facts: {fact_bits}. "
            "Legal rule: Articles 113–116 ГПК РФ govern notices and physical service. "
            "Violation: party was not notified through compliant channels or at the correct address. "
            "Consequence: absentee judgment may lack a valid basis; reversal or reopening may be available; "
            "deadline restoration under Article 112 may be prerequisite for appeal."
        ),
        "service_address_issue": (
            f"Facts: {fact_bits}. "
            "Legal rule: Article 116 ГПК РФ ties delivery to the addressee and household rules; Article 113 "
            "frames permissible notice methods. "
            "Violation: service directed only to a formal address without reaching the party. "
            "Consequence: defective service undermines findings of proper notice and supports challenges to "
            "default or absentee procedure."
        ),
        "foreign_party_issue": (
            f"Facts: {fact_bits}. "
            "Legal rule: Articles 398 and 9 ГПК РФ combine equal procedural rights with language safeguards. "
            "Violation: treating a foreign party as if domestic informal notice sufficed. "
            "Consequence: strengthens the position that cross-border and language protections were mandatory, "
            "not optional."
        ),
        "foreign_service_issue": (
            f"Facts: {fact_bits}. "
            "Legal rule: Article 407 ГПК РФ (with treaties) governs service abroad and judicial assistance. "
            "Violation: documents were not served through required international channels. "
            "Consequence: notice may be legally ineffective; judgment may be vulnerable on procedural grounds."
        ),
        "missed_deadline_due_to_service_issue": (
            f"Facts: {fact_bits}. "
            "Legal rule: Article 112 ГПК РФ allows restoration of missed deadlines for valid reasons. "
            "Violation: deadline missed due to non-receipt or late discovery tied to service defects. "
            "Consequence: court may restore the deadline upon proof, reopening the path to appeal."
        ),
        "appellate_reversal_issue": (
            f"Facts: {fact_bits}. "
            "Legal rule: Article 330 ГПК РФ lists grounds for appellate cancellation or amendment. "
            "Violation: material or procedural errors including notice and interpreter failures. "
            "Consequence: structured appellate attack with paragraph-level mapping to grounds."
        ),
        "alimony_issue": (
            f"Facts: {fact_bits}. "
            "Legal rule: Articles 80–81 СК РФ govern parental maintenance and judicial shares. "
            "Violation: if any, goes to quantum and means — but procedural defects may have prevented a fair "
            "determination. "
            "Consequence: preserve material defenses after procedural relief or in parallel where permitted."
        ),
    }
    return templates.get(
        issue,
        (
            f"Facts: {fact_bits}. "
            "Map this issue to the cited articles in the evidence pack using FACT → RULE → VIOLATION → "
            "CONSEQUENCE. "
            "If the excerpt is thin, flag what additional proof is needed without inventing facts."
        ),
    )

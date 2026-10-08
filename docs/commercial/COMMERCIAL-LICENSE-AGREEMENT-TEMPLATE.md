# AETHRON Commercial Software License Agreement — DRAFT TEMPLATE

**NOT EXECUTED. NOT A GRANT OF RIGHTS. MUST BE REVIEWED BY A QUALIFIED SWEDISH SOFTWARE/IP LAWYER BEFORE USE.**

The parties should sign this agreement together with a completed [commercial order form](ORDER-FORM-TEMPLATE.md). This template is for separately negotiated licensing of project-owned AETHRON software; it does not alter the publicly granted [GPLv3](../../LICENSE) licence or other already granted licences. A public pricing page does **not automatically** grant proprietary rights; only a **signed agreement** and accepted order form can do so.

**Parties.** Licensor: [Nima Khaki or verified licensing legal entity], registration/ID and business address [complete before signing]. Licensee: [full legal name, company registration number, jurisdiction, address]. Effective date: [YYYY-MM-DD]. Agreement reference: [ID]. Authorised signatories: [names/titles].

## 1. Definitions

**Covered Software** means the specifically identified releases, commits, files and original copyright-controlled AETHRON code listed in the executed Order Form, *excluding* third-party source, firmware, models, datasets and other licensors' material unless a separately documented, valid grant exists.

**Licensed Product Family** means a named customer application or integrated product in the Order Form whose end-user purpose/function is substantially the same across its permitted device, model, geographic or cosmetic variants. Separate functionally distinct marketed offerings require separate family entitlements.

**Developer Seat** means a named employee or contractor who modifies, integrates, compiles or directly works with the Covered Software source for Licensee. End users, camera viewers and device operators do not require seats. Permanent seat reassignment is allowed when a developer leaves or changes roles, provided simultaneous excess access is not created.

**Licensed Versions** means the versions and exact source hashes originally delivered under the current paid term and any additional versions the Licensor expressly delivers to Licensee during a subsequent paid annual term.

**Term**, **Order Form**, **Support**, **Permitted Product** and **Founding** are as specified in the signed order and these conditions.

## 2. Separate nonexclusive commercial grant

Subject to a signed Order Form, payment and continuing compliance with this agreement, Licensor grants Licensee a **worldwide, nonexclusive, nontransferable** licence under Licensor-controlled copyright to reproduce, modify, compile, integrate and distribute the Covered Software, in source form internally to its authorised Developer Seats and in embedded/source-unavailable form as part of the named Licensed Product Family/ies, without invoking the AETHRON GPL terms for this separately granted portion. Customer modifications that the customer owns remain customer property, subject to rights in the underlying Covered Software.

Licensee may distribute the licensed Covered Software as part of each approved commercial product to **unlimited end users and devices**, with **no per-unit royalty**, unless the signed Order Form explicitly and separately overrides the deployment scope. Normal hardware variants of one product family do not count as separate families.

The following acts are **not granted** without an explicit amendment: sublicensing Covered Software as an independent SDK/library, reseller/distributor rights to source code standalone, using AETHRON branding as an endorsement, claiming safety certification from Licensor, or offering a competing standalone rebranded AETHRON SDK divorced from a permitted integration. Reasonable binary redistribution through distributors and end-device sales for the authorised product is permitted; distributors receive no broader independent source licence.

The parties acknowledge that the customer may independently elect the GPL route for copies for which GPL rights are valid; this commercial agreement does not revoke those rights.

## 3. Project scope, seats, expansion and updates

Licensee's plan, annual price, maximum Developer Seats, Licensed Product Families, release identifiers and optional support or OEM scope are defined in the signed Order Form. Licence rights apply only to the specified scope. An expansion beyond active source developers or distinct product families requires a mutually signed change order and agreed price, before that expansion is used commercially; *deployment quantity alone* does not trigger a surcharge.

During each paid annual licence term, Licensee is entitled to newly **actually released and expressly delivered** Covered Software versions within the agreed scope. Licensor makes no promise that any particular feature, model, vehicle adapter, hardware support or version will ship by a deadline. No new releases are included after updates/support entitlement expires.

## 4. Continuation of licensed-version rights

Except following termination for an uncured **material breach** under section 12, Licensee retains a **perpetual nonexclusive right** to continue using, patching, building and distributing previously received Licensed Versions (and customer-written modifications of those versions) within **the already authorised product families and terms** even if the annual subscription is not renewed. No continued access to *new* upstream AETHRON releases, support, additional product families, OEM rights or new seats is included after expiry; previously built/deployed devices must not be disabled remotely merely because renewal ceases.

A customer may voluntarily delete Licensed Versions without affecting existing public GPL rights. Continuing distributor licences issued for already sold covered product binaries remain valid to the extent defined by this licence and mandatory law. Separate support and warranty obligations do not continue without a paid service term.

## 5. Pricing, payment, taxes and Founding

Annual plan price, currency (EUR), exclusions, Founding status, payment deadline and billing contact are fixed in the executed Order Form. Unless stated otherwise, amounts are exclusive of applicable VAT and taxes. Default invoices are payable within **30 calendar days**. Parties are responsible for taxes allocated to them under applicable law; Licensor must issue legally correct invoices.

**Founding** applies only when the Order Form has a recorded owner-confirmed slot F001–F025 and both parties have signed. It provides up to 10 Developer Seats and three product families at **€499 per 12-month paid period** for the first **three consecutive annual licence periods**, if all agreed payments are timely and scope remains within plan. A late renewal or scope expansion requires written resolution rather than automatic confiscation of rights to previously licensed versions. The next renewal after those three periods is at the then-current Small Business price unless otherwise agreed. Enquiries do not reserve a slot.

No automatic debit, metered usage billing, remote licence-activation server, per-device fees or automatic renewal is authorised by this template. Any such mechanism requires a distinct written order and cannot be inserted into AETHRON's normal live perception loop.

## 6. Product safety, no certification and site responsibilities

AETHRON's publicly documented software is **research-stage**. Neither the Covered Software, a price quote, a paid licence nor support is an automotive/UAV/medical/industrial safety approval. Licensor makes **no representation** that a vehicle, drone, camera or night sensor will have working OEM camera access, calibrated zero-light perception, regulatory certification, fail-operational control, or any measured production performance absent separate and identified evidence.

Licensee is solely responsible, subject to mandatory applicable law and any separate written SOW, for actual hardware selection, OEM and vendor permission, power/wiring, firmware installation, consumer warnings, privacy, field evaluation, safety case, cybersecurity integration, product certification, aviation/roadworthiness authority approvals and training of operators. Licensee must not connect this research runtime to actuators or rely on it as sole safety protection without separate appropriate qualification. Licensor is not contracted here to provide independent certification or a 24/7 emergency service.

## 7. Third-party components, intellectual property and marks

All Covered Software rights remain with the Licensor and its authorized holders. Only the Licensor-owned portions are licensed here. Third-party libraries, datasets, pretrained weights, firmware, platform SDKs, vendor camera interfaces, patents and trademarks remain subject to their own valid grants. Licensee must independently comply with those licences and cannot obtain third-party proprietary rights by paying Licensor.

Licence notices required by third parties must remain intact. Customer retains copyright in its independently authored software/modifications. This agreement does not require disclosure of Licensee's proprietary code to Licensor. No ownership in Licensee's independent product design is conveyed to Licensor, and Licensor makes no assignment of existing AETHRON IP.

AETHRON and related trademarks may only be used to describe factual compatibility without implying an official endorsement; marketing co-branding requires written authorisation. Prior AETHRON copies licensed under Apache-2.0 retain their historical permissions.

## 8. Source delivery, offline operation and changes

Licensor identifies delivered Covered Software by release tag/source digest and communicates entitlement through the agreed private channel. No internet account, licence-heartbeat, vendor cloud or persistent phone/laptop tether is required by this contract for authorised AETHRON edge operation. This clause addresses licensing architecture, **not** a warranty that a given hardware/firmware configuration works without installation or actual tested hardware.

Licensor has no obligation to supply binaries for platforms it has not built or proven, provide hardware, unlock third-party OEM cameras, sign product firmware or maintain updates after paid entitlement ends. Security patches, model releases and API stability are not guaranteed unless promised in a separately signed SOW.

## 9. Support and services

Active paid commercial licences include best-effort ordinary licensing/install email support, **without guaranteed response times or fix SLAs**. Optional **€99/month priority support** covers up to five new tickets per monthly period with a target first reply within two Swedish business days (09:00–17:00 CET/CEST weekdays, excluding Swedish public holidays); this is not a binding guaranteed repair or uptime SLA. Custom integration is separately estimated/authorised, indicatively **€125–175/hour**. No support entitlement may be interpreted as field safety certification. Service details are described in [support policy](SUPPORT-AND-BILLING.md), as incorporated expressly by the signed Order Form.

## 10. Confidentiality and personal data

Each party shall use reasonably appropriate care for information clearly identified as confidential or inherently confidential commercial/technical material; obligations survive **three years** after agreement termination, except trade secrets for as long as protected by applicable law. Public information, independently developed information, information lawfully known beforehand and compelled disclosure are excluded to the extent lawful. No camera feed, person detection, vehicle location or telemetry must be uploaded to Licensor by default.

The parties remain independently responsible for GDPR and other applicable personal-data regulations. No Data Processing Agreement is incorporated automatically; one must be separately negotiated if the licensor acts as processor for customer personal data. Maintain a secure disclosure route for vulnerability reports.

## 11. Warranty, liability, law and insurance — lawyer review required

**Draft allocation (subject to nonwaivable law and legal review):** The Covered Software is delivered **AS IS**, without express guarantees of uninterrupted operation, fitness for safety-critical deployment or error-free detection, except warranties expressly stated in a separately signed Order Form or SOW. Licensor warrants only that it has authority to issue the rights actually described for Licensor-owned code to the extent it can demonstrate such authority; this is not an across-the-board warranty for independently licensed third-party materials.

To the maximum extent permitted by applicable law, neither party is liable to the other for indirect or consequential commercial damages under this agreement. The aggregate direct contractual liability cap is provisionally **the licence fees paid or payable under the applicable Order Form in the preceding 12 months**, excluding liability that cannot lawfully be capped, fraud, willful misconduct, nonwaivable product liability or other exceptions that a qualified Swedish lawyer determines must be included. **This cap and safety allocation must be reviewed for automotive/UAS and consumer-product law before use.** Neither party gives an unreviewed blanket indemnity here; bespoke OEM indemnities are negotiated separately. Licensee remains responsible for holding appropriate product/public-liability insurance for its hardware and operations where required.

## 12. Term, nonrenewal and termination

Each Order Form runs for **12 months** from its stated start date, unless signed otherwise. No automatic renewal is implied. Either party may decline future renewals without disabling a deployed vehicle/drone or cancelling the perpetual rights under section 4. For a substantial agreement breach, the nonbreaching party may give written notice stating reasonable particulars and allow **30 calendar days to cure** where curable; termination is effective only after the cure period if the breach remains uncured, except where immediate action is required by mandatory law or for an incurable breach. Material licence misuse may terminate alternative proprietary rights as legally applicable; surviving GPL grants remain governed by GPL itself.

Outstanding agreed fees, confidentiality, accrued claims, applicable safety and third-party duties and permitted perpetual-version rights survive as specified here. Termination does not grant either party a right to remotely disable a device.

## 13. Applicable law, disputes and general provisions

Proposed governing law: **Sweden**, excluding conflict rules where permitted. Proposed forum: competent **Stockholm courts**, subject to mandatory jurisdiction/consumer rules and legal review. Parties will first attempt good-faith written resolution within 30 days. Notices go to verified addresses in the Order Form. Assignment by Licensee requires prior written consent except a lawful internal reorganisation agreed in the Order Form. Amendments must be in writing and signed by both parties. Invalid clauses shall be severed without extending IP rights. Neither party may use the other's name or logo for marketing without approval.

Order of precedence for commercial rights: (1) a later signed amendment explicitly identifying the clause changed, (2) the executed Order Form for commercial variables/product scope, (3) this agreement, and (4) any expressly incorporated policies, excluding attempts to alter independent third-party or GPL permissions.

## Signatures (mandatory before any alternative licence exists)

**LICENSOR:** [verified legal name/entity] | Signature: __________________ | Printed name/title: __________________ | Date: __________

**LICENSEE:** [verified legal name/entity] | Signature: __________________ | Printed name/title: __________________ | Date: __________

**ORDER FORM:** [signed reference ID and version]; **APPENDICES:** [explicitly identified third-party licence inventory, optional SOW/support addendum].

**This is a proposed contract template, not a signed licence, purchase confirmation, indemnity, safety certification, or legal opinion.**

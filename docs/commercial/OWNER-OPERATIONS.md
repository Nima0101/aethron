# Commercial programme — owner-only implementation checklist

**Public process specification; no licences or purchases have been executed by writing these documents.** This is a checklist for the person controlling AETHRON's commercial terms, not a public invoice ledger. Do not publish customer identifiers, company financial details, contact addresses, negotiations or serial numbers.

## Before accepting the first payment

1. Arrange review by a Swedish IP/software lawyer for the [agreement](COMMERCIAL-LICENSE-AGREEMENT-TEMPLATE.md), [order form](ORDER-FORM-TEMPLATE.md), licensing chain, Swedish/EU consumer law where applicable, warranty/limitation-of-liability rules, VAT/invoicing requirements and firmware consumer-device GPLv3 obligations.
2. Confirm owned code and contributor grants allow dual licensing. Keep component inventory for GPL/Apache/MIT/BSD/CC0/CDLA models and data. Do not represent third-party IP as yours.
3. Select a verified private business contact method and invoicing entity, and publish it only when ready. Do not invent a company registration/VAT ID, Stripe account or support mailbox.
4. Confirm the current release's actual operational support, package/version IDs and hardware evidence. Do not sell as certified for automotive/UAV or any 24/7 safety SLA until independent evidence and relevant approvals exist.
5. Review support capacity and realistic availability before accepting priority support and engineering SOWs. Decide whether to issue an invoice manually or integrate an appropriate future checkout system.
6. Keep all licensing admin outside a running AETHRON edge unit. Offline entitlement records are administrative; no cloud-dependent boot or expiry kill switch.

## For each customer (manual workflow)

1. Request legal customer name, registration/country, billing details, contact and intended product family. Obtain any company evidence required for Startup eligibility. Use a private channel; no personal data in public issues.
2. Verify number of named source developers including contractors and separately marketed products; decide plan; confirm if OEM rights/custom indemnity/support are requested. Resolve restricted vendor SDK/data/model terms.
3. For **Founding**, allocate a consecutive unique reference F001–F025 only **after** a signed order, and store it in a private restricted ledger; enquiries do not reserve places. Do not publish a vacancy counter without up-to-date records.
4. Fill the [order form](ORDER-FORM-TEMPLATE.md) with plan, price, entity, agreement ID, exact software versions/repositories, product family names, deployment rights, start/end dates, discounts and any overrides. Both parties sign the [contract](COMMERCIAL-LICENSE-AGREEMENT-TEMPLATE.md) and order. Do not backdate or auto-sign.
5. Create a correct invoice and confirm receipt of the agreed payment in the invoicing system. Do not handle payment credentials or publish bank details in the open repo.
6. Privately deliver source/archive/version information and a signed/recorded **offline** entitlement notice, plus the third-party attribution bundle and model inventory. Delivery does not guarantee plug-and-play field qualification.
7. Track renewal **privately** with date and invoice amount; give sufficient advance notice, and respect Founding €499/3-period price lock. Do not disable already installed units on nonrenewal.
8. Track and invoice separately authorised scope expansions or priority support. Keep artefact and customer data minimal and apply a documented retention/deletion policy.
9. Record contract amendments and signed waivers, security incidents, third-party licence exceptions and any IP claims securely. Any future public marketing case study requires the customer's separate approval.

## Not yet implemented

- **No** checkout, automatic subscription billing, signed commercial licence delivery service, customer CRM, public seat counter, online enforcement service or transactional support SLA is claimed.
- Do not add Supabase/Coolify as a runtime dependency for AETHRON. A business operations system is optional and outside the live inference safety loop.
- Prices are published to make the policy understandable; an executed bilateral contract is still needed to confer alternative proprietary rights.

## Publication consistency

Public README, COMMERCIAL-LICENSING.md, FAQ, support policy, price JSON, order and agreement templates and optional static public pricing page should use the same EUR amounts, seat/product entitlements, Founding conditions, support exclusions and licensing disclaimers. The [pricing check](../../scripts/check_commercial_pricing.py) should fail on inconsistencies. Preserve all frozen verification and old model/data licences.

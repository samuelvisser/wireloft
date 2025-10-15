import {createSelectRegistry} from "../utils/selectRegistry";

export const DwMembershipLevelReg = createSelectRegistry("DwMembershipLevel", {
  'WL_ANY': { label: "Highest allowed", help: "Use highest allowed access by your current membership" },
  'FREE':   { label: "Free",   help: "Access to free content only" },
  'INSIDER':   { label: "Insider",   help: "Access to free content and insider content" },
  'INSIDER_PLUS':   { label: "Insider Plus",   help: "Access to insider content and insider plus content" },
  'ALL_ACCESS':   { label: "All Access",   help: "Access to all content" },
});
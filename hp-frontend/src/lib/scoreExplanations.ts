// What each score on the dashboard means and the rule behind it, for the ⓘ
// next to it (client request, 6 Oct: "explain in simple, easy-to-understand
// language how the score is derived").
//
// Each entry has two parts, shown in this order:
//   points - what goes into the score, in plain words
//   rules  - the formula, where the client wants it shown (optional)
// The card can also show the account's own sum ("For this account"), built
// on the page from the live numbers.
//
// No "no data" messages and no internal names - files, code, data vendors,
// rule ids. Every rule here is the one the backend applies: the weights and
// bands come from hp-backend/config/scoring.yaml and the scoring modules.
// Change both together.

export interface ScoreExplanation {
  title: string;
  intro: string;
  points: string[];
  rules?: string[];
  note?: string;
}

export const SCORE_EXPLANATIONS = {
  urgency: {
    title: 'How the urgency score works',
    intro: 'A score from 0 to 100 showing how strong the case is for engaging this account now. It combines four areas:',
    points: [
      'Growth and expansion: how fast the workforce is growing, how much the company is hiring, and recent expansion news.',
      'AI and workstation opportunity: how widely and deeply the company is researching or using AI, its interest in workstations, and recent AI news.',
      'HP solution interest: the company’s strongest interest in an HP product area, whether it is rising, and how close it is to a buying decision.',
      'Workplace technology: the size of the organisation, the operating systems it runs, and how many workplace tools it uses.',
    ],
    rules: [
      'Urgency = Growth × 30% + AI and workstation × 25% + HP solution interest × 25% + Workplace technology × 20%',
      'Each area is scored out of 100, so the total is out of 100, rounded to a whole number.',
      'The score is shown only when at least 60% of the information behind it is available.',
    ],
  },
  urgencyWorkplace: {
    title: 'Workplace Technology and OS Opportunity',
    intro: 'Wherein:',
    points: [
      'Account scale, i.e. the employee range.',
      'Detected OS environment, for example Linux, Windows.',
      'Number of workplace technologies found (workplace technology footprint). A detected technology qualifies only where there is a documented connection to an HP workplace solution, such as HP Workforce Experience Platform (WXP) or HP Anyware.',
    ],
  },
  urgencyAi: {
    title: 'AI and Workstation Opportunity',
    intro: 'Wherein:',
    points: [
      'Breadth: the core AI/ML topic families detected, namely (1) AI / Artificial Intelligence, (2) ML / Machine Learning, (3) Generative AI / GenAI and (4) LLM / Large Language Models / VLLM.',
      'Depth: detailed AI/ML evidence items, such as OpenAI, AI strategy, AI data analytics, AI automation, AI/ML operationalisation, vector database, Azure for ML, AI data management and in-database machine learning.',
      'Workstation intent score, taken directly from the research intent data.',
      'Recent AI initiatives.',
    ],
  },
  urgencyGrowth: {
    title: 'Growth and Expansion Signals',
    intro: 'Wherein:',
    points: [
      'Workforce growth %. This is a LinkedIn workforce proxy, not employee headcount.',
      'Recent hiring volume, i.e. job opening records.',
      'Verified growth and expansion events, such as a new office, headquarters, facility, plant or data centre.',
    ],
  },
  urgencyHpIntent: {
    title: 'HP Solution Intent',
    intro: 'Wherein:',
    points: [
      'HP-category intent score for an HP business area: 3D, Poly, PCs, Workstation, Printers and so on.',
      'Intent trend, i.e. whether the trend for that HP business area is increasing, stable or decreasing.',
      'Buying stage, i.e. whether it shows Decision or Purchase, Consideration, or Awareness.',
      'Research volume, i.e. high, medium or low.',
    ],
  },
  catalysts: {
    title: 'How catalysts are found and ranked',
    intro: 'Catalysts are the company’s strategic priorities, taken from its own filings, reports and announcements.',
    points: [
      'Each catalyst must be backed by actual sentences from those documents; anything that can’t be traced to a source is left out.',
      'At most six are shown, grouped by theme.',
    ],
    rules: [
      'Ranked by the number of supporting sentences, most first.',
      'If two are level: the one mentioned in more different document sections comes first.',
      'If still level: the one with the most recent mention comes first.',
    ],
    note: 'The score on each catalyst is separate: it shows how well that catalyst is backed by evidence, not where it ranks.',
  },
  evidenceStrength: {
    title: 'How the catalyst evidence score works',
    intro: 'A score from 0 to 100 showing how well this catalyst is backed by evidence.',
    points: [
      'Official filings: how many of the company’s own filings and reports mention it.',
      'Recency: how recent the newest supporting source is.',
      'Variety of sources: how many different kinds of sources support it.',
    ],
    rules: [
      'Score = Filings (up to 25) + Recency (up to 25) + Variety of sources (up to 50)',
    ],
  },
  liveSignal: {
    title: 'How the signal score works',
    intro: 'Each news signal is scored out of 10 from three things:',
    points: [
      'Relevance to HP: how directly the news points to something HP can help with.',
      'Recency: newer news scores higher.',
      'Source reliability: news from the company itself or an established publication scores higher.',
    ],
    rules: [
      'Score = Relevance × 50% + Recency × 30% + Source reliability × 20%',
      'Relevance, highest to lowest: a stated need HP can meet · an HP-related technology or workplace project · a major business change (new site, expansion, acquisition, hiring growth) · a weak link to HP · no link',
      'Source, highest to lowest: the company’s own announcement or filing · established news outlet · business data provider · smaller site · unverified',
    ],
  },
  intentHpCategory: {
    title: 'How HP area intent is scored',
    intro: 'Shows how strongly people at this company are researching each of HP’s five business areas: PCs, Workstations, Collaboration, Print and 3D printing.',
    points: [
      'Every topic the company’s people have been researching is matched to the HP area it belongs to. Topics that don’t relate to an HP area are listed separately.',
      'Each topic has a research strength from 0 to 100.',
    ],
    rules: [
      'Area score = the total of its matched topics’ scores ÷ the number of matched topics (an average)',
      'Areas with no matched topic have no score.',
      'If none of the company’s topics relate to HP, each area’s buying-interest score is shown instead.',
    ],
    note: 'Intent shows research activity, not a confirmed plan to buy.',
  },
  opportunityPriority: {
    title: 'How opportunity priority is set',
    intro: 'Each opportunity is given a priority from the evidence behind it:',
    points: [
      'Critical: a specific initiative is confirmed and another independent signal supports it. Example: an announced AI programme plus related AI hiring; a facility expansion plus workforce or meeting-room growth.',
      'High: a specific initiative is confirmed, but there is no second supporting signal. Example: an announced AI programme but no related AI hiring or technology evidence; a confirmed office expansion but no supporting workforce or technology signal.',
      'Medium: no confirmed initiative, but relevant signals suggest a potential opportunity. Example: strong AI, PC or workstation intent without an active programme; relevant AI or engineering hiring; technologies indicating workstation or device relevance.',
      'Low: the evidence is general or indirect, with no clear opportunity. Example: general company growth or a revenue increase; broad hiring with no relevant role or skill connection; generic expansion news without a technology or workplace signal.',
    ],
  },
  techRisk: {
    title: 'How HP fit and risk are labelled',
    intro: 'Each technology area is labelled by how what the company uses today relates to HP.',
    points: [
      'It compares the products found at the company with what HP offers in that area.',
    ],
    rules: [
      'Compete (high risk) = a competitor’s product where HP offers a direct alternative',
      'Complement (low risk) = technology that works alongside HP products',
      'Open opportunity (medium risk) = no product found in this area, so it is open for HP to discuss',
    ],
  },
  messageScore: {
    title: 'How the message score works',
    intro: 'Your message is rated from 0 to 100 on seven qualities: relevance to the reader, business impact, brand recall, clarity, creativity, emotional appeal and the strength of its call to action.',
    points: [
      'Which qualities count most depends on the campaign goal you chose.',
      'A message is scored down if it offers something this reader would not normally be offered, or asks for something outside their role.',
    ],
    rules: [
      'Overall score = each quality’s score × its weight for your goal, added up',
      'Awareness: relevance 30% · impact 20% · brand recall 20% · clarity 15% · creativity 15%',
      'Engagement: relevance 50% · clarity 20% · impact 10% · creativity 10% · emotional appeal 10%',
      'Consideration: relevance 40% · call to action 30% · brand recall 10% · clarity 10% · emotional appeal 10%',
      'Conversion: call to action 30% · brand recall 25% · relevance 15% · impact 15% · clarity 10% · emotional appeal 5%',
      'Advocacy: brand recall 30% · emotional appeal 30% · relevance 15% · clarity 15% · creativity 10%',
      'Offering something outside this reader’s usual range caps relevance at 39; asking for something outside their role caps the call to action at 39.',
      'Bands: 90+ Exceptional · 75+ Strong · 60+ Good · 40+ Average · 20+ Weak · below 20 Poor',
    ],
  },
} satisfies Record<string, ScoreExplanation>;

export type ScoreTopic = keyof typeof SCORE_EXPLANATIONS;

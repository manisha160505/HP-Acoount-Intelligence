// What each score on the dashboard means and the rule behind it, for the ⓘ
// next to it (client request, 6 Oct: "explain in simple, easy-to-understand
// language how the score is derived").
//
// Each entry has two parts, shown in this order:
//   points - what goes into the score, in plain words
//   rules  - the formula and the point rules, written simply
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
  rules: string[];
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
    title: 'Workplace technology and OS opportunity',
    intro: 'Scored from 0 to 100 from the size of the organisation, the operating systems it runs and the workplace tools it uses.',
    points: [
      'Larger organisations score higher.',
      'A mix of operating systems scores higher than a single one.',
      'More workplace tools, such as collaboration and productivity software, score higher.',
    ],
    rules: [
      'Score = Company size (up to 30) + Operating systems (up to 40) + Workplace tools (up to 30)',
      'Company size (staff): 50,000+ = 30 · 10,001–49,999 = 25 · 5,001–10,000 = 20 · 1,001–5,000 = 15 · 251–1,000 = 10 · smaller = 5',
      'Operating systems: Linux + Windows = 40 · Linux + Apple or other = 35 · Windows + Apple or other = 30 · Apple + other = 20 · Linux only = 30 · Windows only = 25 · Apple only = 15 · other only = 10',
      'Workplace tools: 5 or more = 30 · 3–4 = 20 · 1–2 = 10',
    ],
  },
  urgencyAi: {
    title: 'AI and workstation opportunity',
    intro: 'Scored from 0 to 100 from the company’s AI activity and its interest in workstations.',
    points: [
      'How many areas of AI the company is researching or using.',
      'How much AI-related research and technology there is in total.',
      'How much interest the company shows in workstations.',
      'Recent news about the company’s AI activity.',
    ],
    rules: [
      'Score = AI breadth (up to 35) + AI depth (up to 35) + Workstation interest (up to 15) + AI news (up to 15)',
      'AI breadth (of 4 AI areas): 1 area = 14 · 2 = 21 · 3 = 28 · all 4 = 35',
      'AI depth (AI topics and technologies found): 20+ = 35 · 15+ = 28 · 10+ = 21 · 5+ = 14 · 1+ = 7',
      'Workstation interest: the workstation interest score (0–100) scaled down to 15',
      'AI news: 5 points per AI news story in the last year, up to 15',
    ],
  },
  urgencyGrowth: {
    title: 'Growth and expansion signals',
    intro: 'Scored from 0 to 100 from workforce growth, hiring and expansion news.',
    points: [
      'How fast the company’s workforce has been growing.',
      'How many jobs it has advertised over the last year.',
      'Recent news about growth or expansion, such as new sites or acquisitions.',
    ],
    rules: [
      'Score = Workforce growth (up to 25) + Hiring (up to 50) + Expansion news (up to 25)',
      'Workforce growth: 20%+ = 25 · 10%+ = 20 · 5%+ = 15 · 1%+ = 7.5',
      'Hiring (jobs advertised in the last year): 200+ = 50 · 100+ = 40 · 50+ = 30 · 20+ = 20 · 5+ = 10',
      'Expansion news: 10 points per story in the last year, up to 25',
    ],
  },
  urgencyHpIntent: {
    title: 'HP solution intent',
    intro: 'Scored from 0 to 100 from the company’s strongest interest in an HP product area.',
    points: [
      'How strong that interest is.',
      'Whether it is rising or falling.',
      'How close the company is to a buying decision.',
      'How much research activity there is behind it.',
    ],
    rules: [
      'Score = Interest strength (up to 60) + Trend (up to 10) + Buying stage (up to 15) + Research volume (up to 15)',
      'Interest strength: the strongest HP area’s interest score (0–100) scaled down to 60',
      'Trend: rising = 10 · steady = 5 · falling = 0',
      'Buying stage: decision or purchase = 15 · consideration = 10 · awareness = 5',
      'Research volume: high = 15 · medium = 10 · low = 5',
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
      'Filings: 5 points for each filing that mentions it, up to 25',
      'Recency of the newest source: within 1 year = 25 · 2 years = 20 · 3 years = 15 · 5 years = 10 · older = 5',
      'Variety: 10 points for each kind of source (company filings, company announcements, investor material, government sources, independent media), up to 50',
    ],
    note: 'It measures how well the catalyst is supported, not how important it is.',
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
      'Score = Relevance × 50% + Recency × 30% + Source reliability × 20% (each out of 10)',
      'Relevance: a stated need HP can meet = 10 · an HP-related technology or workplace project = 8 · a major business change (new site, expansion, acquisition, hiring growth) = 6 · a weak link to HP = 3 · no link = 0',
      'Recency: within 7 days = 10 · 30 days = 8 · 90 days = 6 · 6 months = 4 · 1 year = 2 · older = 0',
      'Source: the company’s own announcement or filing = 10 · established news outlet = 8 · business data provider = 6 · smaller site = 3 · unverified = 0',
      'Label: 8 or more = Critical · 6 or more = High · 4 or more = Medium · below 4 = Low',
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
  intentCategoryInterest: {
    title: 'How these area scores work',
    intro: 'Each HP area is scored from 0 to 100 for how much buying interest the company shows in it.',
    points: [
      'A higher score means stronger signs of interest in that area, such as research activity.',
      'Each area also shows a buying stage, from early awareness to a purchase decision.',
    ],
    rules: [
      'Scores are shown as received from a specialist research provider, without changes.',
      'Areas are listed from the highest score to the lowest.',
    ],
    note: 'Intent shows research activity, not a confirmed plan to buy.',
  },
  intentTopic: {
    title: 'What the topic score means',
    intro: 'A score from 0 to 100 for how much more than usual people at this company have been reading about the topic.',
    points: [
      'A higher score means a stronger, more recent rise in interest.',
      'It reflects research across the whole company, not one person.',
    ],
    rules: [
      'Scores are shown as received from a specialist research provider, without changes.',
      'Filter: 70+ and 85+ show only the strongest topics.',
    ],
    note: 'Intent shows research activity, not a confirmed plan to buy.',
  },
  opportunityPriority: {
    title: 'How opportunity priority is set',
    intro: 'Each opportunity is ranked by how strong and how timely the evidence for it is.',
    points: [
      'Direct evidence: the company is clearly working on this initiative.',
      'Timing: a recent event makes it time-sensitive.',
    ],
    rules: [
      'Critical = direct evidence + a timing event',
      'High = direct evidence, no timing event yet',
      'Medium = related signals only, no direct evidence',
      'Low = background context only',
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
  hpRecommendation: {
    title: 'How recommendation confidence works',
    intro: 'Each HP recommendation carries two labels: how certain the fit is, and how much evidence supports it.',
    points: [
      'Fit: whether the company’s technology matches this HP offering and whether the timing is right.',
      'Evidence: how many separate kinds of data point to the same need.',
    ],
    rules: [
      'Confirmed = the technology fits + a recent event makes it timely',
      'Likely = the technology fits, nothing time-sensitive yet',
      'Discovery = the area looks open or related; worth exploring in conversation',
      'Opportunity = 2 or more separate kinds of data support it · Conversation starter = 1 strong signal · Context only = background',
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

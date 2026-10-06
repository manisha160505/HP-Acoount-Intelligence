// What each score on the dashboard means, in plain language, for the ⓘ next
// to it (client request, 6 Oct: "explain in simple, easy-to-understand
// language how the score is derived ... just mention the key parameters").
//
// Written for a seller seeing the page for the first time. Deliberately
// leaves out: exact points for sub-factors, "no data" messages, and any
// internal name - files, code, data vendors, rule ids. Every statement here
// matches the scoring the backend actually does; change both together.

export interface ScoreExplanation {
  title: string;
  intro: string;
  points: string[];
  note?: string;
}

export const SCORE_EXPLANATIONS = {
  urgency: {
    title: 'How the urgency score works',
    intro: 'A score from 0 to 100 showing how strong the case is for engaging this account now. It combines four areas:',
    points: [
      'Growth and expansion (the largest share): how fast the workforce is growing, how much the company is hiring, and recent news about expansion.',
      'AI and workstation opportunity: how widely and deeply the company is researching or using AI, its interest in workstations, and recent AI news.',
      'HP solution interest: the company’s strongest interest in an HP product area, whether that interest is rising, and how close it is to a buying decision.',
      'Workplace technology: the size of the organisation, the operating systems it runs, and how many workplace tools it uses.',
    ],
    note: 'The score is shown only when enough of this information is available for the account.',
  },
  urgencyWorkplace: {
    title: 'Workplace technology and OS opportunity',
    intro: 'Scored from 0 to 100 from three things:',
    points: [
      'The size of the organisation: larger companies score higher.',
      'The operating systems it runs: a mix of systems scores higher than a single one.',
      'How many workplace tools it uses, such as collaboration and productivity software.',
    ],
  },
  urgencyAi: {
    title: 'AI and workstation opportunity',
    intro: 'Scored from 0 to 100 from four things:',
    points: [
      'How many areas of AI the company is researching or using.',
      'How much AI-related research and technology there is in total.',
      'How much interest the company shows in workstations.',
      'Recent news about the company’s AI activity.',
    ],
  },
  urgencyGrowth: {
    title: 'Growth and expansion signals',
    intro: 'Scored from 0 to 100 from three things:',
    points: [
      'How fast the company’s workforce has been growing.',
      'How many jobs it has advertised over the last year.',
      'Recent news about growth or expansion, such as new sites or acquisitions.',
    ],
  },
  urgencyHpIntent: {
    title: 'HP solution intent',
    intro: 'Scored from 0 to 100 from the company’s strongest interest in an HP product area:',
    points: [
      'How strong that interest is.',
      'Whether it is rising or falling.',
      'How close the company is to a buying decision.',
      'How much research activity there is behind it.',
    ],
  },
  evidenceStrength: {
    title: 'How evidence strength works',
    intro: 'A score from 0 to 100 showing how well this priority is backed by evidence. It looks at three things:',
    points: [
      'Official filings: how many of the company’s own filings and reports mention it.',
      'Recency: how recent the newest supporting source is.',
      'Variety of sources: how many different kinds of sources support it, such as company filings, company announcements, investor material, government sources and independent media.',
    ],
    note: 'It measures how well the priority is supported, not how important it is.',
  },
  liveSignal: {
    title: 'How the signal score works',
    intro: 'Each news signal is scored out of 10 from three things:',
    points: [
      'Relevance to HP (half of the score): how directly the news points to something HP can help with, from a stated technology or purchasing need down to a general business change.',
      'Recency (about a third): newer news scores higher.',
      'Source reliability (the rest): news from the company itself or an established publication scores higher than news from less established sites.',
    ],
    note: 'Signals scoring 8 or more are marked Critical, 6 or more High, 4 or more Medium, and the rest Low.',
  },
  intentHpCategory: {
    title: 'How HP area intent is scored',
    intro: 'Shows how strongly people at this company are researching each of HP’s five business areas: PCs, Workstations, Collaboration, Print and 3D printing.',
    points: [
      'Every topic the company’s people have been researching is matched to the HP area it belongs to. Topics that don’t relate to an HP area are listed separately.',
      'An area’s score is the average research strength of the topics matched to it, from 0 to 100.',
      'Where no researched topic relates to HP, the scores come from a separate measure of buying interest in each HP area.',
    ],
    note: 'Intent shows research activity, not a confirmed plan to buy.',
  },
  intentCategoryInterest: {
    title: 'How these area scores work',
    intro: 'Each HP area is scored from 0 to 100 for how much buying interest the company shows in it, based on its online research activity.',
    points: [
      'A higher score means more, and more focused, research in that area.',
      'Each area also shows a buying stage, from early awareness to a purchase decision.',
      'The scores are shown as received from a specialist research provider and are not adjusted.',
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
    note: 'Intent shows research activity, not a confirmed plan to buy.',
  },
  opportunityPriority: {
    title: 'How opportunity priority is set',
    intro: 'Each opportunity is ranked by how strong and how timely the evidence for it is:',
    points: [
      'Critical: there is direct evidence the company is working on this, and a recent event makes it timely.',
      'High: there is direct evidence of the initiative, but nothing yet makes it time-sensitive.',
      'Medium: related signals point to it, without direct evidence of an initiative.',
      'Low: background context only.',
    ],
  },
  techRisk: {
    title: 'How HP fit and risk are labelled',
    intro: 'Each technology area is labelled by how it relates to HP:',
    points: [
      'Compete (high risk): the company uses a competitor’s product where HP offers a direct alternative.',
      'Complement (low risk): the company’s technology works alongside HP products.',
      'Open opportunity (medium risk): no product was found in this area, so it is open for HP to discuss.',
    ],
  },
  hpRecommendation: {
    title: 'How recommendation confidence works',
    intro: 'Each HP recommendation carries two labels.',
    points: [
      'Confirmed: the company’s technology fits this HP offering and a recent event makes it timely.',
      'Likely: the technology fits, but nothing yet makes it time-sensitive.',
      'Discovery: the area looks open or related, and is worth exploring in conversation.',
      'Opportunity / Conversation starter / Context only: how much independent evidence supports it, from two or more separate kinds of data, to one strong signal, to background only.',
    ],
  },
  messageScore: {
    title: 'How the message score works',
    intro: 'Your message is rated from 0 to 100 on seven qualities: relevance to the reader, business impact, brand recall, clarity, creativity, emotional appeal and the strength of its call to action.',
    points: [
      'Which qualities count most depends on the campaign goal you chose. For example, a message aimed at conversion gives the call to action the most weight.',
      'A message is scored down if it offers something this reader would not normally be offered, or asks for something outside their role.',
      'Overall bands: 90 and above Exceptional, 75 Strong, 60 Good, 40 Average, 20 Weak, below 20 Poor.',
    ],
  },
} satisfies Record<string, ScoreExplanation>;

export type ScoreTopic = keyof typeof SCORE_EXPLANATIONS;

/**
 * The words of the product tour and of each feature's help (?) button.
 *
 * Client, 17 Oct: people new to the platform should be walked through every
 * feature on their first sign-in, in very simple English, and be able to see
 * a feature's walkthrough again at any time. Each feature has one overview
 * card (Skip / Dive in) and a few detail cards that point at parts of the
 * screen.
 *
 * `target` names a `data-tour="..."` element on the dashboard. A card whose
 * target is not on screen (a section the account has no data for) is shown in
 * the middle of the page instead, so the tour never gets stuck.
 */

export interface TourCard {
  title: string;
  body: string;
  /** Short tips shown as a list under the body. */
  points?: string[];
  target?: string;
}

export interface FeatureTour {
  overview: TourCard;
  details: TourCard[];
}

export const TOUR_WELCOME: TourCard = {
  title: 'Welcome to HP Account Intelligence',
  body:
    'This short tour shows you what each part of the platform does. ' +
    'It takes about two minutes. For each feature, choose Dive in to see more, or Skip to move on.',
  points: [
    'The menu on the left lists every feature.',
    'Everything you see is about the account selected at the top of that menu.',
  ],
  target: 'sidebar',
};

export const TOUR_FINISH: TourCard = {
  title: "You're all set",
  body:
    'That is the whole platform. Click the ? next to any feature title to see its walkthrough again, ' +
    'or use Take the tour to start this tour from the beginning.',
  target: 'tour-button',
};

export const FEATURE_TOURS: Record<string, FeatureTour> = {
  executive_dashboard: {
    overview: {
      title: 'Executive Dashboard',
      body:
        'A one-page summary of the account: who they are, how big they are, ' +
        'how urgent they are for HP, and what they care about most.',
      target: 'exec-profile',
    },
    details: [
      {
        title: 'Company profile',
        body: 'What the company does, where it is based, its industry and its parent company.',
        target: 'exec-profile',
      },
      {
        title: 'Key metrics',
        body:
          'Size and money figures. "Filed" figures come from the company\'s own reports; ' +
          'other figures are size ranges from data providers.',
        target: 'exec-metrics',
      },
      {
        title: 'Urgency score',
        body:
          'A score out of 100 for how ready the account looks to buy from HP right now, ' +
          'with the four reasons behind it.',
        target: 'exec-urgency',
      },
      {
        title: 'Strategic priorities',
        body:
          'The goals the company has stated, each with the evidence behind it. ' +
          'Use these to link your pitch to what they already want.',
        target: 'exec-priorities',
      },
    ],
  },

  recent_news_signals: {
    overview: {
      title: 'Live Signals',
      body:
        'Recent news and events about the account, such as new projects, expansions or leadership changes. ' +
        'The most useful ones are at the top.',
      target: 'signals-header',
    },
    details: [
      {
        title: 'A signal',
        body:
          'Each card is one news item with its date and a score out of 10. ' +
          '"Implication for HP" tells you why it matters for your sale.',
        target: 'signals-first',
      },
      {
        title: 'Filters',
        body: 'Narrow the list by type of news or by score.',
        target: 'signals-filters',
      },
    ],
  },

  intent_demand_signals: {
    overview: {
      title: 'Intent & Demand Signals',
      body:
        'What the company is researching online and hiring for, matched to HP\'s product areas. ' +
        'It shows where they may be ready to buy.',
      target: 'intent-header',
    },
    details: [
      {
        title: 'So what for HP',
        body: 'A short summary of what this research interest means for you.',
        target: 'intent-sowhat',
      },
      {
        title: 'Interest by HP area',
        body:
          'One score for each HP area: PCs, workstations, Poly (meetings), print and 3D. ' +
          'A higher score means more research on that topic.',
        target: 'intent-units',
      },
      {
        title: 'Hiring signals',
        body: 'What jobs the company is advertising, and the technology named in those job ads.',
        target: 'intent-hiring',
      },
    ],
  },

  stakeholder_map: {
    overview: {
      title: 'Stakeholder Map',
      body: 'The people at this account, grouped by department and sorted by seniority.',
      target: 'stakeholder-header',
    },
    details: [
      {
        title: 'Search and filter',
        body: 'Find a person by name, title or department, or narrow the list by seniority or department.',
        target: 'stakeholder-filters',
      },
      {
        title: 'Senior contacts',
        body:
          'The most senior people come first. Each card has contact details and a short ' +
          '"How to open" idea for starting the conversation.',
        target: 'stakeholder-senior',
      },
      {
        title: 'Export',
        body: 'Download the contact list as a spreadsheet.',
        target: 'stakeholder-export',
      },
    ],
  },

  solution_narrative_opportunity_map: {
    overview: {
      title: 'Opportunity Map',
      body:
        'Ready-made sales ideas ("plays") for HP products and services, ' +
        "each based on the account's own evidence.",
      target: 'opportunity-header',
    },
    details: [
      {
        title: 'HP opportunity plays',
        body:
          'Each play says what to sell, why it fits this account, which HP products to use ' +
          'and who to talk to. The proof quotes come from the account\'s own data.',
        target: 'opportunity-plays',
      },
    ],
  },

  tech_landscape: {
    overview: {
      title: 'Technographic Map',
      body:
        'The technology this company already uses, and how each one relates to HP: ' +
        'a competitor, a partner fit, or an opening for HP.',
      target: 'tech-header',
    },
    details: [
      {
        title: 'Strategic read',
        body: 'A short summary of what their technology means for HP.',
        target: 'tech-read',
      },
      {
        title: 'Technology by HP area',
        body: 'Their tools grouped into HP areas, with the vendor names and the HP angle for each.',
        target: 'tech-categories',
      },
      {
        title: 'Opportunities only',
        body: 'Switch this on to see only the areas where HP has an opening.',
        target: 'tech-toggle',
      },
    ],
  },

  objection_playbook: {
    overview: {
      title: 'Objection Playbook',
      body:
        'Push-back you may hear from this account, and how to answer it. ' +
        'These are likely objections, not things anyone has actually said.',
      target: 'objection-header',
    },
    details: [
      {
        title: 'Objection cards',
        body:
          'Click a card to open it. You will see a suggested answer, the evidence behind it, ' +
          'a question to ask back, and HP proof where there is one.',
        target: 'objection-cards',
      },
    ],
  },

  content_studio: {
    overview: {
      title: 'Content Studio',
      body:
        'Writes an email, a LinkedIn message or a one-pager for this account in seconds, ' +
        "using only the account's own data.",
      target: 'studio-header',
    },
    details: [
      {
        title: 'Choose what to write',
        body: 'Pick who you are writing to, the format and the HP topic, then click Generate.',
        target: 'studio-controls',
      },
      {
        title: 'Your draft',
        body: 'The draft appears here. Read it, then copy or download it. Always check it before you send it.',
        target: 'studio-output',
      },
    ],
  },

  strategy_chat: {
    overview: {
      title: 'Strategy Chat',
      body:
        'Ask questions about this account in plain English and get answers with sources. ' +
        "It only answers from this account's data.",
      target: 'chat-header',
    },
    details: [
      {
        title: 'How to ask',
        body: 'You get the best answers when you:',
        points: [
          'Ask about this account only.',
          'Ask one clear question at a time, and name the person, product or topic.',
          'Do not ask about other accounts or general topics. The chat will say no.',
          'If the data does not have the answer, the chat tells you so instead of guessing.',
        ],
        target: 'chat-welcome',
      },
      {
        title: 'Suggested questions',
        body: 'Not sure where to start? Click one of these ready-made questions.',
        target: 'chat-suggestions',
      },
      {
        title: 'Type your question',
        body: 'Type here and press Enter. Each answer shows the sources it used.',
        target: 'chat-input',
      },
    ],
  },

  message_evaluator: {
    overview: {
      title: 'Message Evaluator',
      body:
        'Paste a message you wrote and get a score and tips for the person you are sending it to. ' +
        'It can also improve the message for you.',
      target: 'evaluator-header',
    },
    details: [
      {
        title: 'Step by step',
        body:
          'Follow the steps from left to right: add your message, choose who it is for, then see ' +
          'the scores, feedback on each phrase, a summary and an optional rewrite.',
        target: 'evaluator-steps',
      },
    ],
  },
};

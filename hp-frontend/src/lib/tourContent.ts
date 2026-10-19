/**
 * The words of the product tour, and of each feature's own tour (Take the tour).
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
  /** One target, or several in order of preference: the first one on screen
   *  is lit, and a later one only once the first has had time to appear. */
  target?: string | string[];
  /** Asked of the dashboard when the card shows, e.g. open an Evaluator step. */
  action?: string;
  /** Added under the body when the card fell back past its first target -
   *  the screen it describes is not open yet. */
  notYet?: string;
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
    "That is the whole platform. To see a feature's walkthrough again, open it and click " +
    'Take the tour at the top of the page.',
  target: 'tour-button',
};

/** How to ask Strategy Chat: its tour card and the box on its empty screen. */
export const CHAT_TIPS: string[] = [
  'Ask about this account only. Questions about other accounts or general topics are declined.',
  'Ask one clear question at a time, and name the person, product or topic.',
  'Say what you are trying to do, e.g. "I am meeting their CIO next week about AI PCs."',
  'Say what you want back: a short answer, 3 bullet points, an email draft or a 90-day plan.',
  'Follow up in the same chat to go deeper, e.g. "Tell me more about the second point."',
  "Answers come only from this account's data, with sources. If the data does not have it, the chat says so.",
];

const EVALUATE_FIRST = 'You will see this after you evaluate a message.';

function evaluatorStep(key: string, title: string, body: string, notYet?: string): TourCard {
  return {
    title, body, notYet,
    action: `evaluator:${key}`,
    target: [`evaluator-panel-${key}`, `evaluator-step-${key}`],
  };
}

/** After the last feature, for sellers (admins have no My Activity button). */
export const MY_ACTIVITY_CARD: TourCard = {
  title: 'My Activity',
  body:
    'Your own use of the platform: time spent, feature views and logins, ' +
    'the features you use most, and the accounts you viewed most.',
  target: 'my-activity',
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
        title: 'Additional context',
        body:
          'You can also give additional context, if any: talking points, recent news, or anything ' +
          'the draft should mention. It is optional.',
        target: 'studio-context',
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
        points: CHAT_TIPS,
        target: 'chat-welcome',
      },
      {
        title: 'Suggested questions',
        body:
          'Not sure where to start? Click one of these, or try: "Who should I approach first for an ' +
          'AI PC refresh, and why?" or "What objections might their CFO raise, and how do I answer them?"',
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
    // One card per step of the Evaluator. Each opens its step when the user
    // could open it themselves; otherwise it points at the step's name. The
    // tour never runs an evaluation or a rewrite.
    details: [
      evaluatorStep('inputs', 'Step 1: Inputs',
        'Choose Lite (quick) or Deep (more detail), who you are writing to, your goal and the format, ' +
        'then paste your message. You can also load a message you checked before.'),
      evaluatorStep('persona', 'Step 2: Persona',
        'See who you are writing to: their role, goals, pain points and what they care about.',
        'You will see this after you fill in step 1.'),
      evaluatorStep('confirm', 'Step 3: Confirm',
        'Check it is the right person, then click Confirm Persona & Evaluate. Scoring takes a few seconds.',
        'You will see this after you fill in step 1.'),
      evaluatorStep('scores', 'Step 4: Scores',
        'A total score out of 100, plus seven scores with a reason for each, and format checks.',
        EVALUATE_FIRST),
      evaluatorStep('phrases', 'Step 5: Phrases',
        'Your message line by line, marked Keep, Improve or Change. Tick the changes you want.',
        EVALUATE_FIRST),
      evaluatorStep('summary', 'Step 6: Summary',
        'Strengths and weaknesses in short. Deep mode also shows how the reader might react.',
        EVALUATE_FIRST),
      evaluatorStep('rewrite', 'Step 7: Rewrite',
        'Rewrites your message using only the changes you ticked, and shows what changed.',
        'You will see this after you evaluate a message, tick changes and click Rewrite.'),
    ],
  },
};

// ---------------------------------------------------------------------------
// The admin pages' tour (client, 17 Oct): Accounts, Platform, Users and
// Analytics, in the order of the admin menu. Rules is left out. Remembered
// apart from the dashboard's tour, so an admin sees each once.

export const ADMIN_TOUR_WELCOME: TourCard = {
  title: 'Welcome to the admin pages',
  body:
    'This short tour shows the four admin pages: Accounts, Platform, Users and Analytics. ' +
    'For each page, choose Dive in to see more, or Skip to move on.',
  target: 'admin-nav',
};

export const ADMIN_TOUR_FINISH: TourCard = {
  title: "You're all set",
  body:
    "To see a page's walkthrough again, open it and click Take the tour at the top. " +
    "Each account's dashboard has its own tour too.",
  target: 'admin-tour-button',
};

export const ADMIN_TOURS: Record<string, FeatureTour> = {
  accounts: {
    overview: {
      title: 'Accounts',
      body:
        'The same list sellers see. As an admin you see every account here. ' +
        "Click an account to open its dashboard.",
      target: 'admin-accounts-header',
    },
    details: [
      {
        title: 'Search and filter',
        body: 'Search by company name, or filter by Urgency Score to find the accounts most ready to buy.',
        target: 'admin-accounts-controls',
      },
      {
        title: 'The account list',
        body:
          'Each row is one account with its Urgency Score out of 100. ' +
          "Click a row to open that account's dashboard.",
        target: 'admin-accounts-list',
      },
    ],
  },

  platform: {
    overview: {
      title: 'Platform',
      body:
        'Where you look after the accounts themselves: add new ones, update their data, ' +
        'and choose which ones sellers can see.',
      target: 'admin-platform-header',
    },
    details: [
      {
        title: 'Create New Account',
        body: 'Adds a new company. Then use Manage to upload its data.',
        target: 'admin-platform-create',
      },
      {
        title: 'Search',
        body: 'Find an account by name.',
        target: 'admin-platform-search',
      },
      {
        title: 'The account table',
        body:
          'Status shows if sellers can see the account (Active) or not (Hidden). ' +
          'Last Updated shows when it last changed.',
        target: 'admin-platform-table',
      },
      {
        title: 'Manage',
        body:
          "Opens the account's own page. There you upload its data files and rebuild its features. " +
          'That page has its own tour: click Take the tour there.',
        target: 'admin-platform-manage',
      },
      {
        title: 'More actions',
        body:
          "The menu next to Manage opens the account's dashboard, or hides the account from sellers " +
          'without deleting anything. Show to sellers brings it back.',
        target: 'admin-platform-hide',
      },
    ],
  },

  // The page Manage opens (/admin/accounts/<id>). Help only: Take the tour
  // shows it, but the first-visit tour does not, since it has no one account
  // to open (see ADMIN_HELP_PAGES in components/tour/AdminTour.tsx).
  account: {
    overview: {
      title: 'Manage an account',
      body:
        'Everything about one account: its details, its data files and its writing guidance. ' +
        'Each tab below is one part.',
      target: 'admin-account-header',
    },
    details: [
      {
        title: 'Account Details',
        body: "Change the account's name. Below it, see which sellers can open this account.",
        target: 'admin-account-tab-details',
      },
      {
        title: 'Sellers with access',
        body:
          'The sellers who can open this account. Admins can open every account, so they are not listed. ' +
          'To change who has access, use Accounts on the Users page.',
        target: 'admin-account-sellers',
      },
      {
        title: 'Data',
        body:
          'Upload or replace the data files for this account, one dataset at a time. ' +
          "The account's features are then updated from them by the platform team.",
        target: 'admin-account-tab-data',
      },
      {
        title: 'Instructions',
        body: 'Custom guidelines for this account only, such as topics to focus on or regional notes.',
        target: 'admin-account-tab-instructions',
      },
      {
        title: 'Guardrails',
        body: 'Rules for this account only, such as wording or claims to avoid.',
        target: 'admin-account-tab-guardrails',
      },
    ],
  },

  users: {
    overview: {
      title: 'Users',
      body:
        'Add people, choose which accounts each seller can open, and reset passwords. ' +
        'Admins can see every account.',
      target: 'admin-users-header',
    },
    details: [
      {
        title: 'Add user',
        body:
          'Enter their email and role and pick their accounts. You get a temporary password to give them; ' +
          'they choose their own when they first sign in.',
        target: 'admin-users-add',
      },
      {
        title: 'Search and filter',
        body: 'Search by email or name, or show only sellers, only admins, or sellers with no accounts yet.',
        target: 'admin-users-filters',
      },
      {
        title: 'The people list',
        body: 'Each person\'s role, the accounts they can open, whether they are active, and when they last signed in.',
        target: 'admin-users-table',
      },
      {
        title: 'Change a user',
        body:
          'Accounts changes which accounts a seller can open. The menu next to it resets a password ' +
          'or deactivates someone. Their history is kept.',
        target: 'admin-users-actions',
      },
      {
        title: 'Activity log',
        body: 'Every change made to users: who made it, to whom, and when.',
        target: 'admin-users-tabs',
      },
    ],
  },

  analytics: {
    overview: {
      title: 'Analytics',
      body: 'How sellers use the platform. Admin activity is not counted.',
      target: 'admin-analytics-header',
    },
    details: [
      {
        title: 'Dates',
        body: 'Pick the dates to look at. Dates are in UTC.',
        target: 'admin-analytics-range',
      },
      {
        title: 'Totals',
        body: 'For those dates: how many users, who was active in the last 7 days, logins, feature views and time spent.',
        target: 'admin-analytics-tiles',
      },
      {
        title: 'Features and days',
        body:
          'Which features are used most, how many sellers were active each day, and the most viewed accounts. ' +
          'Click a bar to see who.',
        target: 'admin-analytics-charts',
      },
      {
        title: 'Each seller',
        body: 'Every seller with their logins, last login, and how much they used each feature.',
        target: 'admin-analytics-users',
      },
    ],
  },
};

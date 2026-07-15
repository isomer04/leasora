// UI/API Constants

export const CLAUSE_TYPES = {
  rental_term: 'Rental Term',
  maintenance: 'Maintenance',
  liability: 'Liability Insurance',
  assignment: 'Assignment Rights',
  termination: 'Early Termination',
  renewal: 'Renewal',
  other: 'Other',
} as const;

export const LEASE_STATUS = {
  active: 'Active',
  expired: 'Expired',
  pending: 'Pending',
  draft: 'Draft',
} as const;

export const API_ENDPOINTS = {
  health: '/health',
  leases: {
    list: '/leases',
    detail: (id: string) => `/leases/${id}`,
    create: '/leases',
    update: (id: string) => `/leases/${id}`,
    delete: (id: string) => `/leases/${id}`,
  },
  ask: '/ask',
  compare: '/compare',
  upload: '/upload',
  eval: '/eval',
} as const;

export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 10,
  MAX_PAGE_SIZE: 100,
} as const;

export const VALIDATION = {
  MAX_FILE_SIZE: 50 * 1024 * 1024, // 50MB
  ALLOWED_FILE_TYPES: ['application/pdf'],
  MAX_QUESTION_LENGTH: 1000,
  MAX_LEASE_NAME_LENGTH: 255,
} as const;

export const TIMEOUTS = {
  API_REQUEST: 30000, // 30s
  UPLOAD: 300000, // 5min
} as const;

export const ERROR_MESSAGES = {
  NETWORK_ERROR: 'Network error. Please check your connection.',
  INVALID_FILE: 'Invalid file format. Please upload a PDF.',
  FILE_TOO_LARGE: 'File is too large. Maximum 50MB allowed.',
  REQUIRED_FIELD: 'This field is required.',
  NOT_FOUND: 'The requested resource was not found.',
  SERVER_ERROR: 'Server error. Please try again later.',
} as const;

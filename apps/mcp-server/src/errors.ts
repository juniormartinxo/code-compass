export class ToolInputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ToolInputError';
  }
}

export class ToolExecutionError extends Error {
  constructor(
    public readonly code:
      | 'BAD_REQUEST'
      | 'FORBIDDEN'
      | 'NOT_FOUND'
      | 'UNSUPPORTED_MEDIA'
      | 'EMBEDDING_FAILED'
      | 'EMBEDDING_INVALID',
    message: string,
  ) {
    super(message);
    this.name = 'ToolExecutionError';
  }
}

declare const validators: {
  integerFields: readonly string[];
  validateScene: (value: unknown) => boolean;
  validateSession: (value: unknown) => boolean;
  validateHealth: (value: unknown) => boolean;
};
export = validators;

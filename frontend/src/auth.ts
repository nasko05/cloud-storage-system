import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserAttribute,
  CognitoUserSession,
  CognitoUserPool
} from 'amazon-cognito-identity-js';
import { config } from './config';

const userPool = new CognitoUserPool({
  UserPoolId: config.userPoolId,
  ClientId: config.clientId
});

export const register = async (email: string, password: string): Promise<CognitoUser> =>
  new Promise((resolve, reject) => {
    const attributeList = [new CognitoUserAttribute({ Name: 'email', Value: email })];

    userPool.signUp(email, password, attributeList, [], (error, result) => {
      if (error || !result?.user) {
        reject(error ?? new Error('Registration failed'));
        return;
      }
      resolve(result.user);
    });
  });

export const confirmRegistration = async (email: string, code: string): Promise<string> =>
  new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });
    user.confirmRegistration(code, true, (error, result) => {
      if (error || !result) {
        reject(error ?? new Error('Confirmation failed'));
        return;
      }
      resolve(result);
    });
  });

export const login = async (email: string, password: string): Promise<string> =>
  new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });
    const authDetails = new AuthenticationDetails({ Username: email, Password: password });

    user.authenticateUser(authDetails, {
      onSuccess: (result) => resolve(result.getIdToken().getJwtToken()),
      onFailure: (error) => reject(error),
      newPasswordRequired: () => reject(new Error('Password change required'))
    });
  });

export const logout = (): void => {
  const user = userPool.getCurrentUser();
  if (user) {
    user.signOut();
  }
};

export const getToken = async (): Promise<string | null> =>
  new Promise((resolve) => {
    const user = userPool.getCurrentUser();
    if (!user) {
      resolve(null);
      return;
    }

    user.getSession((error: Error | null, session: CognitoUserSession | null) => {
      if (error || !session?.isValid()) {
        resolve(null);
        return;
      }

      resolve(session.getIdToken().getJwtToken());
    });
  });

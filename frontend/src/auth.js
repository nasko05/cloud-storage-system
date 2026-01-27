import { CognitoUserPool, CognitoUser, AuthenticationDetails } from 'amazon-cognito-identity-js';
import { config } from './config';

const userPool = new CognitoUserPool({
  UserPoolId: config.userPoolId,
  ClientId: config.clientId
});

export const login = (email, password) => {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });
    const authDetails = new AuthenticationDetails({ Username: email, Password: password });
    
    user.authenticateUser(authDetails, {
      onSuccess: (result) => resolve(result.getAccessToken().getJwtToken()),
      onFailure: (err) => reject(err),
      newPasswordRequired: () => reject(new Error('Password change required'))
    });
  });
};

export const logout = () => {
  const user = userPool.getCurrentUser();
  if (user) user.signOut();
};

export const getToken = () => {
  return new Promise((resolve, reject) => {
    const user = userPool.getCurrentUser();
    if (!user) return resolve(null);
    
    user.getSession((err, session) => {
      if (err || !session.isValid()) return resolve(null);
      resolve(session.getAccessToken().getJwtToken());
    });
  });
};

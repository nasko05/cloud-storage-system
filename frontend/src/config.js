export const config = {
  apiEndpoint: process.env.REACT_APP_API_ENDPOINT,
  userPoolId: process.env.REACT_APP_USER_POOL_ID,
  clientId: process.env.REACT_APP_COGNITO_CLIENT_ID,
  region: process.env.REACT_APP_REGION || 'eu-central-1'
};

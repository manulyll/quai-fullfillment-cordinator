import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession
} from "amazon-cognito-identity-js";
import { config } from "./config";

const userPool = new CognitoUserPool({
  UserPoolId: config.cognitoUserPoolId,
  ClientId: config.cognitoClientId
});

export type AuthSession = {
  idToken: string;
  accessToken: string;
};

const getCurrentCognitoUser = (): CognitoUser | null => userPool.getCurrentUser();

export const signIn = (username: string, password: string): Promise<AuthSession> =>
  new Promise((resolve, reject) => {
    const authDetails = new AuthenticationDetails({
      Username: username,
      Password: password
    });
    const cognitoUser = new CognitoUser({
      Username: username,
      Pool: userPool
    });

    cognitoUser.authenticateUser(authDetails, {
      onSuccess: (session) =>
        resolve({
          idToken: session.getIdToken().getJwtToken(),
          accessToken: session.getAccessToken().getJwtToken()
        }),
      onFailure: (error) => reject(error)
    });
  });

export const getCurrentSession = (): Promise<AuthSession | null> =>
  new Promise((resolve) => {
    const user = getCurrentCognitoUser();
    if (!user) {
      resolve(null);
      return;
    }
    user.getSession((error: Error | null, session: CognitoUserSession | null) => {
      if (error || !session?.isValid()) {
        resolve(null);
        return;
      }
      resolve({
        idToken: session.getIdToken().getJwtToken(),
        accessToken: session.getAccessToken().getJwtToken()
      });
    });
  });

export const signOut = (): void => {
  const user = getCurrentCognitoUser();
  user?.signOut();
};

package main

import (
	"boulevard-extractor/model"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/machinebox/graphql"
)

// Confit
type Config struct {
        // Job-defined
        TaskNum    string
        AttemptNum string

		// User-defined
		BoulevardCredentials BoulevardCredentials
}

// Boulevard Credentials
type BoulevardCredentials struct {
	Url string `json:"url"`
	BusinessID string `json:"business_id"`
	AppID string `json:"app_id"`
	ApiKey string `json:"api_key"`
	ApiSecret string `json:"api_secret"`	
}

// Boulevard Client
type BoulevardClient struct { 
	GraphqlClient *graphql.Client
	Url string
	BasicHttpCredentials string
}
	
func NewBoulevardClient( creds *BoulevardCredentials ) ( *BoulevardClient ){ 
	// Create the Headers
	basicHttpCreds := createHttpBasicCredentials( creds )

	// Create the graphql createGraphqlClient
	graphqlClient := graphql.NewClient(
		creds.Url,
	)

	// Crete the Boulevard newBoulevardClient
	blvdClient := &BoulevardClient {
		GraphqlClient: graphqlClient,
		BasicHttpCredentials: basicHttpCreds,
	}

	return blvdClient
}

func ( client *BoulevardClient ) Run(req *graphql.Request, ctx context.Context, respData interface{}) error {

	// Add the authorization headers
	req.Header.Add("Authorization", "Basic " + client.BasicHttpCredentials)
	log.Println(req.Header)
	if err := client.GraphqlClient.Run(ctx, req, respData); err != nil {
		return err
	}
	return nil
}

// Nodes
// Pagination
type Cursor string
type PageInfo struct {
	EndCursor Cursor `json:"cursor"`
	HasNextPage bool `json:"hasNextPage"`
	HasPreviousPage bool `json:"hasPreviousPage"`
	StartCursor Cursor `json:"startCursor"`
}

// Location
type LocationConnection struct {
	Edges []LocationEdge `json:"edges"`
	PageInfo PageInfo `json:"PageInfo"`
}

type LocationEdge struct {
	Cursor Cursor `json:"cursor"`
	Node Location `json:"node"`
}
type Location struct {
	// TODO: Implement
}	
type Address struct { 
	// TODO Implement
}

// Memberships
type MembershipConnection struct {
	Edges []MembershipEdge `json:"edges"`
	PageInfo PageInfo `json:"PageInfo"`
}
type MembershipEdge struct {
	Cursor Cursor `json:"cursor"`
	Node model.Membership `json:"node"` // We are trying to extract the proto types right away, so we don't have to go through the pain the ass of converting later 
}

// Orders
type OrderConnection struct {
	Edges []MembershipEdge `json:"edges"`
	PageInfo PageInfo `json:"PageInfo"`
}
type OrderEdge struct {
	Cursor Cursor `json:"cursor"`
	Node model.Order `json:"node"` // We are trying to extract the proto types right away, so we don't have to go through the pain the ass of converting later 
}


func configFromEnv() (Config, error) {

        // Job-defined
        taskNum := os.Getenv("CLOUD_RUN_TASK_INDEX")
        attemptNum := os.Getenv("CLOUD_RUN_TASK_ATTEMPT")

		// User defined
		secretsPath := os.Getenv("SECRETS_PATH")
		log.Println("Loading boulevard credentials")
		boulevardCredsPath := fmt.Sprintf("%s/boulevard_credentials.json", secretsPath)
		file, err := os.Open(boulevardCredsPath)
		if err != nil {
			log.Fatal("Couldn't retrieve secret: ", err)
		}
		data, err := io.ReadAll(file)
		log.Println("Boulevard credentials: ", data)

		var boulevardCreds BoulevardCredentials 
		json.Unmarshal(data, &boulevardCreds)
		
		boulevardCreds.Url = os.Getenv("BOULEVARD_URL")

		log.Println("Boulevard Url: ", boulevardCreds.Url)
		log.Println("Boulevard Business ID: ", boulevardCreds.BusinessID)
		log.Println("Boulevard App ID: ", boulevardCreds.AppID)
		log.Println("Boulevard Api Key: ", boulevardCreds.ApiKey)

        config := Config{
                TaskNum:    taskNum,
                AttemptNum: attemptNum,
				BoulevardCredentials: boulevardCreds,
        }
        return config, nil
}

// GQL credentials
func createHttpBasicCredentials(creds *BoulevardCredentials) ( string ) {
	// Create the HTTP Headers
    prefix := "blvd-admin-v1"
    timestamp := fmt.Sprintf("%d", time.Now().Unix())

    payload := []byte(prefix + creds.BusinessID + timestamp)
    rawKey, _ := base64.StdEncoding.DecodeString(creds.ApiSecret)
    h := hmac.New(sha256.New, rawKey)
    h.Write(payload)
    signature := h.Sum(nil)
    signatureBase64 := base64.StdEncoding.EncodeToString(signature)
    token := signatureBase64 + string(payload)
    httpBasicPayload := creds.ApiKey + ":" + token
	httpBasicCredentials := base64.StdEncoding.EncodeToString([]byte(httpBasicPayload))
	return httpBasicCredentials
}

func hello(c *gin.Context){
	c.String(http.StatusOK, "Hello There")
}

func main() {
	router := gin.Default()
	router.GET("/hello", hello)

	router.Run()
}

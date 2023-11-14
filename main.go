package main

import (
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

// Config
type Config struct {
	// User-defined
	BoulevardUrl string
	BoulevardCredentials *BoulevardCredentials
}

// Boulevard Credentials
type BoulevardCredentials struct {
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
	
func NewBoulevardClient( url string, creds *BoulevardCredentials ) ( *BoulevardClient ){ 
	// Create the Headers
	basicHttpCreds := createHttpBasicCredentials( creds )

	// Create the graphql createGraphqlClient
	graphqlClient := graphql.NewClient(url)

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


// Job
type Job struct {
	Entity string `json:"entity"`
	Query string `json:"query"`
	Status string `json:"status"`
	Message string `json:"message"` // Latest status message
}
func NewJob(entity string, query string) (*Job, error) {
	// Maybe include some validation here
	// For example, some jobs will take queries, others won't
	newJob := &Job {
		entity,
		query,
		"CREATED",
		"",
	}
	return newJob, nil
}
func (j *Job) Run() error {
	
	log.Println("Running job...")


	// Load the Query
	query, err := loadQuery(j.Entity)
	if err != nil {
		msg := fmt.Sprintf("Failed to load query - %v", err)
		j.Fail(msg)
		return fmt.Errorf(msg)
	}

	// Add parameters to the query as needed
	query.Var("first", 100)
	if j.Query != "" {
		query.Var("query", j.Query)
	}

	// For testing: query a single page
	// And also - hard code it to work with locations
	var responseData ConnectionQueryResponse[*Location]
	err = blvd.Run(query, context.Background(), &responseData)
	if err != nil{
		msg := fmt.Sprintf("Failed to execute query - %v", err)
		j.Fail(msg)
		return fmt.Errorf(msg)
	}

	log.Println(responseData)
	
	j.Status = "SUCCESS"

	return nil
}

func (j *Job) Fail( msg string) {
	j.Message = msg
	j.Status = "FAILED"
}

// Core types
type ConnectionQueryResponse[T Node] map[string]*Connection[T]

type Connection[T Node] struct {
	Edges *[]Edge[T] `json:"edges"`
	PageInfo *PageInfo `json:"pageInfo"`
}

type Edge[T Node] struct {
	Cursor Cursor `json:"cursor"`
	Node *T `json:"node"`
}

// Pagination
type Cursor string
type PageInfo struct {
	EndCursor Cursor `json:"cursor"`
	HasNextPage bool `json:"hasNextPage"`
	HasPreviousPage bool `json:"hasPreviousPage"`
	StartCursor Cursor `json:"startCursor"`
}

// Nodes
// Most important ones: Location, Memberships, Orders, Staff, Appointments
type Node interface{ 
	GetID() string
}

// Location
type Address struct {
	Street   string `json:"street"`
	City     string `json:"city"`
	State    string `json:"state"`
	ZipCode  string `json:"zipCode"`
	Country  string `json:"country"`
}

type Email string

type Coordinates struct {
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
}

type PaymentOption struct {
	Name  string  `json:"name"`
	Price float64 `json:"price"`
}

type PhoneNumber string

type Tz string

type Location struct {
	Address               Address                `json:"address"`
	BusinessName          string                 `json:"businessName"`
	ContactEmail          Email                  `json:"contactEmail"`
	Coordinates           Coordinates            `json:"coordinates"`
	ExternalID            string                 `json:"externalId"`
	ID                    string                 `json:"id"`
	IsRemote              bool                   `json:"isRemote"`
	Name                  string                 `json:"name"`
	Phone                 PhoneNumber            `json:"phone"`
	Tz                   Tz                     `json:"tz"`
	Website              string                 `json:"website"`
}
func (l *Location) GetID() string {
	return l.ID
}



func configFromEnv() (*Config, error) {

		// User defined
		secretName := os.Getenv("SECRET_NAME")
		log.Printf("Loading secret: %s\n", secretName)
		boulevardCredsPath := fmt.Sprintf("/mnt/secrets/%s", secretName)
		file, err := os.Open(boulevardCredsPath)
		if err != nil {
			log.Fatal("Couldn't retrieve secret: ", err)
		}
		data, err := io.ReadAll(file)

		log.Println("Here")
		var boulevardCreds BoulevardCredentials 
		json.Unmarshal(data, &boulevardCreds)

		
		log.Println("Here 2")
		cfg := &Config{
			BoulevardUrl: os.Getenv("BOULEVARD_URL"),
			BoulevardCredentials: &boulevardCreds,
		}
		return cfg, nil
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

func loadQuery(entity string) (*graphql.Request, error) {
	// Define the path where the GraphQL queries are stored
	queryPath := fmt.Sprintf("graphql/list_%s.graphql", entity)

	// Read the contents of the GraphQL query file
	file, err := os.Open(queryPath)
	if err != nil {
		return nil, fmt.Errorf("Couldn't load query: %v", err)
	}
	queryBytes, err := io.ReadAll(file)

	// Create a new GraphQL request with the read query
	req := graphql.NewRequest(string(queryBytes))

	return req, nil
}


// Handlers
func hello(c *gin.Context){
	c.String(http.StatusOK, "Hello There")
}


func createJob(c *gin.Context) {
	entity := c.Query("entity")
	query := c.DefaultQuery("query", "")

	log.Printf("Creating new job for entity %s with query %s.", entity, query)
	job, err := NewJob(entity, query) 
	if err != nil {
		errMsg := fmt.Sprintf("Error creating job: %v", err)
		log.Println(errMsg)
		c.JSON(http.StatusBadRequest, gin.H{"error": errMsg})
		return
	}

	log.Print("Starting job execution")
	err = job.Run()
	if err != nil {
		errMsg := fmt.Sprintf("Error executing job: %v", err)
		log.Println(errMsg)
		c.JSON(http.StatusBadRequest, gin.H{"error": errMsg})
		return
	}

	log.Print("Evaluate Job execution")
	if job.Status != "SUCCESS" {
		c.JSON(http.StatusBadRequest, job)
		return
	}
	
	
	c.JSON(http.StatusOK, job)
	return
}

// Initialization functions
// 1 . Boulevard Client
var config *Config 
var blvd BoulevardClient

func initConfig() {
	var err error
	config, err = configFromEnv()
	if err != nil {
		log.Fatal("Failed to initialize config: ", err)
	}
}

func initBoulevardClient() {
	blvd = *NewBoulevardClient(config.BoulevardUrl, config.BoulevardCredentials)
}


func main() {

	// Initialization
	initConfig()
	initBoulevardClient()

	router := gin.Default()
	router.GET("/", hello)
	
	// Jobs
	router.POST("/jobs", createJob)

	router.Run()
}

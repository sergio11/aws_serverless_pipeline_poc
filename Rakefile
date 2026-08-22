COMPOSE_FILE = ENV.fetch("COMPOSE_FILE", "compose.yaml")
FLOCI_ENDPOINT = ENV.fetch("FLOCI_ENDPOINT", "http://localhost:4566")
FLOCI_SERVICE = ENV.fetch("FLOCI_SERVICE", "floci")
FLOCI_CONTAINER = ENV.fetch("FLOCI_CONTAINER", "poc-floci")
UI_SERVICE = ENV.fetch("UI_SERVICE", "floci-ui")
UI_CONTAINER = ENV.fetch("UI_CONTAINER", "poc-floci-ui")
BACKEND_ENDPOINT = ENV.fetch("BACKEND_ENDPOINT", "http://localhost:8000")
BACKEND_SERVICE = ENV.fetch("BACKEND_SERVICE", "backend")
BACKEND_CONTAINER = ENV.fetch("BACKEND_CONTAINER", "poc-backend")
BACKEND_DIR = ENV.fetch("BACKEND_DIR", "backend")
WORKER_SERVICE = ENV.fetch("WORKER_SERVICE", "lambda-worker")
WORKER_CONTAINER = ENV.fetch("WORKER_CONTAINER", "poc-lambda-worker")
LAMBDA_FUNCTION = ENV.fetch("LAMBDA_FUNCTION", "poc-local-document-processor")
E2E_SERVICE = ENV.fetch("E2E_SERVICE", "e2e")
INTEGRATION_SERVICE = ENV.fetch("INTEGRATION_SERVICE", "integration")
INTEGRATION_CONTAINER = ENV.fetch("INTEGRATION_CONTAINER", "poc-integration")
TERRAFORM_DIR = ENV.fetch("TERRAFORM_DIR", "terraform")
TERRAFORM_SERVICE = ENV.fetch("TERRAFORM_SERVICE", "terraform")
TERRAFORM_VOLUME = ENV.fetch("TERRAFORM_VOLUME", "terraform-workdir")
TERRAFORM_VAR_FILE = ENV.fetch("TERRAFORM_VAR_FILE", "environments/local/terraform.tfvars")

def run_command(*args)
  command = args.join(" ")
  puts command
  success = system(*args)
  abort "Command failed: #{command}" unless success
end

def ensure_terraform_volume
  existing = `podman volume inspect #{TERRAFORM_VOLUME} 2>&1`
  return if $?.success?
  run_command("podman", "volume", "create", TERRAFORM_VOLUME)
end

def sync_terraform_to_volume
  ensure_terraform_volume
  host_path = File.expand_path(TERRAFORM_DIR)
  run_command(
    "podman", "run", "--rm",
    "-v", "#{host_path}:/src:ro",
    "-v", "#{TERRAFORM_VOLUME}:/terraform",
    "--entrypoint", "sh",
    "aws-local-poc_terraform", "-c",
    "cp -r /src/. /terraform/"
  )
  # Fix permissions lost during copy from Windows host
  run_command(
    "podman", "run", "--rm",
    "-v", "#{TERRAFORM_VOLUME}:/terraform",
    "--entrypoint", "sh",
    "aws-local-poc_terraform", "-c",
    "find /terraform/.terraform -type f -name 'terraform-provider-*' -exec chmod +x {} +; true"
  )
end

def sync_terraform_from_volume
  host_path = File.expand_path(TERRAFORM_DIR)
  run_command(
    "podman", "run", "--rm",
    "-v", "#{TERRAFORM_VOLUME}:/terraform",
    "-v", "#{host_path}:/host",
    "--entrypoint", "sh",
    "aws-local-poc_terraform", "-c",
    "cp -r /terraform/. /host/"
  )
end

def run_terraform(*args)
  ensure_terraform_volume
  sync_terraform_to_volume
  run_command(
    "podman", "run", "--rm",
    "--network", "poc-network",
    "-e", "AWS_ACCESS_KEY_ID=test",
    "-e", "AWS_SECRET_ACCESS_KEY=test",
    "-e", "AWS_DEFAULT_REGION=eu-west-1",
    "-v", "#{TERRAFORM_VOLUME}:/terraform",
    "-w", "/terraform",
    "aws-local-poc_terraform", *args
  )
  sync_terraform_from_volume
end

def terraform_output_json
  require "json"
  ensure_terraform_volume
  sync_terraform_to_volume
  output = `podman run --rm --network poc-network -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test -e AWS_DEFAULT_REGION=eu-west-1 -v #{TERRAFORM_VOLUME}:/terraform -w /terraform aws-local-poc_terraform output -json`
  sync_terraform_from_volume
  abort "terraform output failed" unless $?.success?
  JSON.parse(output)
end

def command_available?(command)
  extensions = ENV.fetch("PATHEXT", "").split(";")
  extensions = [""] if extensions.empty?

  ENV.fetch("PATH", "").split(File::PATH_SEPARATOR).any? do |path|
    extensions.any? do |extension|
      File.executable?(File.join(path, "#{command}#{extension}"))
    end
  end
end

namespace :doctor do
  desc "Check required local developer tools"
  task :tools do
    {
      "ruby" => "Ruby runtime for Rake tasks",
      "rake" => "Task runner",
      "podman" => "Container runtime",
      "podman-compose" => "Compose runner for Podman",
      "curl" => "HTTP readiness checks",
      "terraform" => "Infrastructure provisioning",
      "aws" => "AWS CLI diagnostics"
    }.each do |command, purpose|
      status = command_available?(command) ? "OK" : "MISSING"
      puts "#{command.ljust(15)} #{status.ljust(8)} #{purpose}"
    end
  end
end

namespace :compose do
  desc "Validate the Compose file"
  task :config do
    run_command("podman-compose", "-f", COMPOSE_FILE, "config")
  end

  desc "Build all local images"
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build")
  end

  desc "Show running POC containers"
  task :status do
    run_command("podman", "ps", "--filter", "name=poc-", "--format", "{{.Names}} {{.Status}} {{.Ports}}")
  end

  desc "Show Compose logs"
  task :logs do
    run_command("podman-compose", "-f", COMPOSE_FILE, "logs")
  end
end

namespace :floci do
  desc "Validate the Podman Compose configuration"
  task :config do
    run_command("podman-compose", "-f", COMPOSE_FILE, "config")
  end

  desc "Start the Floci local AWS emulator"
  task :up do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", FLOCI_SERVICE)
  end

  desc "Wait until Floci responds on FLOCI_ENDPOINT"
  task :wait do
    retries = ENV.fetch("FLOCI_WAIT_RETRIES", "30").to_i
    delay = ENV.fetch("FLOCI_WAIT_DELAY_SECONDS", "2").to_i
    ready = false

    1.upto(retries) do |attempt|
      if system("curl", "-fsS", FLOCI_ENDPOINT, out: File::NULL, err: File::NULL)
        puts "Floci is ready at #{FLOCI_ENDPOINT}"
        ready = true
        break
      end

      puts "Waiting for Floci at #{FLOCI_ENDPOINT} (#{attempt}/#{retries})"
      sleep delay
    end

    abort "Floci did not become ready at #{FLOCI_ENDPOINT}" unless ready
  end

  desc "Start Floci and wait until it is ready"
  task start: [:up, :wait]

  desc "Show Floci container status"
  task :status do
    run_command("podman", "ps", "--filter", "name=#{FLOCI_CONTAINER}", "--format", "{{.Names}} {{.Status}} {{.Ports}}")
  end

  desc "Show Floci logs"
  task :logs do
    run_command("podman", "logs", FLOCI_CONTAINER)
  end

  desc "Stop the local Compose environment"
  task :down do
    run_command("podman-compose", "-f", COMPOSE_FILE, "down")
  end
end

namespace :infra do
  desc "Initialize Terraform"
  task :init do
    run_terraform("init")
  end

  desc "Format Terraform files"
  task :fmt do
    run_terraform("fmt", "-recursive")
  end

  desc "Validate Terraform configuration"
  task validate: :init do
    run_terraform("validate")
  end

  desc "Show Terraform plan for local infrastructure"
  task plan: ["floci:start", :init] do
    run_terraform("plan", "-var-file=#{TERRAFORM_VAR_FILE}")
  end

  desc "Apply Terraform local infrastructure"
  task apply: ["floci:start", :init] do
    run_terraform("apply", "-var-file=#{TERRAFORM_VAR_FILE}")
  end

  desc "Destroy Terraform local infrastructure"
  task destroy: ["floci:start", :init] do
    run_terraform("destroy", "-var-file=#{TERRAFORM_VAR_FILE}")
  end

  desc "Show Terraform outputs"
  task :output do
    run_terraform("output")
  end

  desc "Package Lambda worker into a deployment zip"
  task :package_lambda do
    run_command("bash", "scripts/package-lambda.sh")
  end

  desc "Upload Lambda zip to S3 on Floci"
  task upload_lambda: ["floci:start", :package_lambda] do
    outputs = terraform_output_json
    bucket = outputs.dig("s3_bucket", "value")

    run_command(
      "aws", "--endpoint-url", FLOCI_ENDPOINT,
      "s3", "cp", "tmp/lambda/worker.zip",
      "s3://#{bucket}/lambda/document-processor.zip"
    )
  end

  desc "Generate .env from Terraform outputs"
  task :env do
    outputs = terraform_output_json

    env_content = [
      "S3_BUCKET=#{outputs.dig('s3_bucket', 'value') || ''}",
      "DYNAMODB_TABLE=#{outputs.dig('dynamodb_table', 'value') || ''}",
      "SQS_QUEUE_URL=#{outputs.dig('sqs_queue_url', 'value') || ''}",
      "SQS_DLQ_URL=#{outputs.dig('sqs_dlq_url', 'value') || ''}",
    ].join("\n") + "\n"

    File.write(".env", env_content)
    puts "Generated .env from Terraform outputs"
  end

  desc "Apply infrastructure, upload Lambda, and generate .env"
  task deploy: [:apply, :upload_lambda, :env]

  desc "Reconcile orphaned documents stuck in CREATED or PROCESSING state"
  task :reconcile do
    max_age = ENV.fetch("RECONCILE_MAX_AGE_MINUTES", "10")
    run_command(
      "python", "scripts/reconcile_orphan_documents.py",
      "--endpoint-url", FLOCI_ENDPOINT,
      "--table", "documents",
      "--queue", "document-events",
      "--max-age-minutes", max_age,
    )
  end
end

namespace :backend do
  desc "Build the backend container"
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", BACKEND_SERVICE)
  end

  desc "Run backend tests"
  task test: :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", BACKEND_SERVICE, "pytest", "tests", "--cov=app", "--cov-report=term-missing", "--cov-fail-under=98")
  end

  desc "Start the backend service"
  task up: "floci:start" do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", BACKEND_SERVICE)
  end

  desc "Wait until the backend health endpoint responds"
  task :wait do
    endpoint = "#{BACKEND_ENDPOINT}/health"
    retries = ENV.fetch("BACKEND_WAIT_RETRIES", "30").to_i
    delay = ENV.fetch("BACKEND_WAIT_DELAY_SECONDS", "2").to_i
    ready = false

    1.upto(retries) do |attempt|
      if system("curl", "-fsS", endpoint, out: File::NULL, err: File::NULL)
        puts "Backend is ready at #{endpoint}"
        ready = true
        break
      end

      puts "Waiting for backend at #{endpoint} (#{attempt}/#{retries})"
      sleep delay
    end

    abort "Backend did not become ready at #{endpoint}" unless ready
  end

  desc "Start backend and wait until it is ready"
  task start: [:up, :wait]

  desc "Show backend container status"
  task :status do
    run_command("podman", "ps", "--filter", "name=#{BACKEND_CONTAINER}", "--format", "{{.Names}} {{.Status}} {{.Ports}}")
  end

  desc "Show backend logs"
  task :logs do
    run_command("podman", "logs", BACKEND_CONTAINER)
  end

  desc "Run backend HTTP smoke check"
  task smoke: :start do
    run_command("curl", "-fsS", "#{BACKEND_ENDPOINT}/health")
  end

  desc "Generate HTML coverage report for backend"
  task coverage: :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", BACKEND_SERVICE, "pytest", "tests", "--cov=app", "--cov-report=html", "--cov-report=term-missing", "--cov-fail-under=98")
  end
end

namespace :worker do
  desc "Build the Lambda-style worker container"
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", WORKER_SERVICE)
  end

  desc "Run worker tests"
  task test: :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", WORKER_SERVICE, "pytest", "tests", "--cov=handler", "--cov-report=term-missing", "--cov-fail-under=98")
  end

  desc "Process one SQS receive cycle and exit (fallback when Lambda unavailable)"
  task run_once: ["floci:start", :build] do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "-T", WORKER_SERVICE, "python", "handler.py", "--once")
  end

  desc "Start the polling worker (fallback when Lambda unavailable)"
  task start: ["floci:start", :build] do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", WORKER_SERVICE)
  end

  desc "Show worker container status"
  task :status do
    run_command("podman", "ps", "--filter", "name=#{WORKER_CONTAINER}", "--format", "{{.Names}} {{.Status}} {{.Ports}}")
  end

  desc "Show worker logs"
  task :logs do
    run_command("podman", "logs", WORKER_CONTAINER)
  end
end

namespace :lambda do
  desc "Invoke the Lambda function directly (for testing)"
  task invoke: "floci:start" do
    payload = {
      "Records" => [{
        "body" => JSON.generate({
          "event_type" => "DocumentCreated",
          "document_id" => ENV.fetch("TEST_DOCUMENT_ID", "test-doc")
        })
      }]
    }
    run_command(
      "aws", "lambda", "invoke",
      "--function-name", LAMBDA_FUNCTION,
      "--endpoint-url", FLOCI_ENDPOINT,
      "--payload", JSON.generate(payload),
      "/dev/stdout"
    )
  end

  desc "Show Lambda function configuration"
  task :config do
    run_command(
      "aws", "lambda", "get-function",
      "--function-name", LAMBDA_FUNCTION,
      "--endpoint-url", FLOCI_ENDPOINT,
      "--query", "Configuration",
      "--output", "json"
    )
  end

  desc "List event source mappings"
  task :esm do
    run_command(
      "aws", "lambda", "list-event-source-mappings",
      "--function-name", LAMBDA_FUNCTION,
      "--endpoint-url", FLOCI_ENDPOINT,
      "--output", "json"
    )
  end

  desc "Package Lambda code for deployment"
  task :package do
    run_command("bash", "scripts/package-lambda.sh")
  end
end

namespace :integration do
  desc "Build the integration test container"
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", INTEGRATION_SERVICE)
  end

  desc "Run integration tests against Floci"
  task test: ["infra:deploy", :build] do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", INTEGRATION_SERVICE, "pytest", "tests")
  end
end

namespace :e2e do
  desc "Build the end-to-end test container"
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", E2E_SERVICE)
  end

  desc "Run end-to-end document workflow tests"
  task test: ["infra:deploy", "backend:start", :build] do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", E2E_SERVICE, "pytest", "tests")
  end
end

namespace :ui do
  desc "Start the Floci UI console"
  task start: "floci:start" do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", UI_SERVICE)
  end

  desc "Stop the Floci UI console"
  task :down do
    run_command("podman-compose", "-f", COMPOSE_FILE, "stop", UI_SERVICE)
  end

  desc "Show Floci UI container status"
  task :status do
    run_command("podman", "ps", "--filter", "name=#{UI_CONTAINER}", "--format", "{{.Names}} {{.Status}} {{.Ports}}")
  end

  desc "Show Floci UI logs"
  task :logs do
    run_command("podman", "logs", UI_CONTAINER)
  end
end

namespace :test do
  desc "Run unit/API tests for backend and worker"
  task unit: ["backend:test", "worker:test"]

  desc "Run integration tests against Floci"
  task integration: "integration:test"

  desc "Run end-to-end tests"
  task e2e: "e2e:test"

  desc "Run all tests"
  task all: [:unit, :integration, :e2e]

  desc "Destroy infra, rebuild, and run full test suite"
  task rebuild: ["infra:destroy", "infra:deploy", "test:unit", "test:integration", "test:e2e"]
end

namespace :verify do
  desc "Run hardening verification"
  task hardening: ["doctor:tools", "ci", "compose:status"]
end

namespace :acceptance do
  desc "Run final POC acceptance checks"
  task :check do
    Rake::Task["doctor:tools"].invoke
    Rake::Task["ci"].invoke
    puts "Acceptance checks completed. Review docs/acceptance-report.md for remaining tooling gaps."
  end
end

desc "Start the local AWS emulator"
task up: "floci:start"

desc "Stop the local AWS emulator"
task down: "floci:down"

desc "Provision local AWS-compatible infrastructure"
task infra: "infra:apply"

desc "Run all tests"
task test: "test:all"

desc "Check required local developer tools"
task doctor: "doctor:tools"

desc "Build all local images"
task build: "compose:build"

desc "Show running POC containers"
task status: "compose:status"

desc "Run CI validation locally"
task ci: ["compose:config", "test:all"]

desc "Run hardening verification"
task verify: "verify:hardening"

desc "Run final POC acceptance checks"
task acceptance: "acceptance:check"

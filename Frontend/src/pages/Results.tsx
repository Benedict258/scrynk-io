import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useLocation, useNavigate } from "react-router-dom";
import { Mail, ExternalLink, ArrowLeft, RefreshCw } from "lucide-react";

interface ResultsState {
  emails: string[];
  postUrl: string;
  status: 'success' | 'failure';
}

const Results = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as ResultsState;

  // Redirect to extract page if no data
  if (!state) {
    navigate('/extract');
    return null;
  }

  const { emails, postUrl, status } = state;

  return (
    <div className="min-h-screen bg-background py-16">
      <div className="container mx-auto px-4 max-w-4xl">
        <div className="mb-8">
          <Button
            variant="ghost"
            onClick={() => navigate('/extract')}
            className="font-kode mb-4 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Extract
          </Button>
          <h1 className="font-bungee text-4xl text-primary mb-2">
            Extraction Results
          </h1>
          <p className="font-kode text-muted-foreground">
            Results from your email extraction request
          </p>
        </div>

        <div className="space-y-6">
          {/* Status Card */}
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="font-rampart text-lg flex items-center gap-2">
                <Mail className="w-5 h-5" />
                Extraction Status
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between mb-4">
                <Badge 
                  variant={status === 'success' ? 'default' : 'destructive'}
                  className="font-kode"
                >
                  {status === 'success' ? 'SUCCESS' : 'FAILED'}
                </Badge>
                <div className="font-kode text-sm text-muted-foreground">
                  {emails.length} emails found
                </div>
              </div>
              <div className="space-y-2">
                <div className="font-kode text-sm text-foreground">
                  <span className="text-muted-foreground">Source URL:</span>
                </div>
                <div className="flex items-center gap-2">
                  <code className="font-kode text-sm bg-muted px-2 py-1 rounded flex-1">
                    {postUrl}
                  </code>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => window.open(postUrl, '_blank')}
                    className="font-kode"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Emails Card */}
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="font-rampart text-lg">
                Extracted Emails ({emails.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {emails.length === 0 ? (
                <div className="text-center py-8">
                  <Mail className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <p className="font-kode text-muted-foreground">
                    No emails found in this post
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {emails.map((email, index) => (
                    <div
                      key={index}
                      className="font-kode text-sm bg-muted px-3 py-2 rounded border border-border hover:bg-secondary/50 transition-colors"
                    >
                      {email}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="flex gap-4 justify-center">
            <Button
              onClick={() => navigate('/extract')}
              className="font-rampart bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Try Again
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate('/status')}
              className="font-rampart"
            >
              View Status
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Results;
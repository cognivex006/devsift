import { Component } from '@angular/core';
@Component({ selector: 'app-card', template: '<span>https://docs.example.test</span>' })
export class CardComponent {
  endpoint = process.env.API_URL;
  load() { return fetch(this.endpoint); }
}
